"""Claude Code `Stop` hook: after every turn, append what was asked and done to
work log/<date>/<user>.md.

One file per person per day (work log/2026-11-05/reejay.md, work log/2026-11-05/abhinav.md), so two people never edit the same
file and there are no merge conflicts. The files are meant to be committed: they are the daily record of work done with
Claude on this repo.

Safety: anything key-shaped is replaced by [redacted] before it is written, text is cut short, and this script never
fails the turn (every error is swallowed, exit code is always 0). Standard library only.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_DIR = "work log"  # work log/<date>/<user>.md, one file per person per day
PROMPT_CHARS = 500
ANSWER_CHARS = 700
MAX_FILES = 25
_EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}

# Key-shaped values: known prefixes, assignments to names that sound secret, and long mixed letter+digit tokens.
_PREFIXED = re.compile(
    r"\b(?:sk-|nvapi-|ghp_|gho_|github_pat_|xox[abp]-|AKIA|AIza)[A-Za-z0-9_\-]{8,}"
)
_ASSIGNED = re.compile(
    r"(?i)(\b[\w.-]*(?:key|token|secret|password|passwd|credential)[\w.-]*\s*[=:]\s*)(?:\"[^\"]+\"|'[^']+'|\S+)"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}")
_LONG = re.compile(r"[A-Za-z0-9_\-]{28,}")
# a real git command starts a shell statement; the words inside a file being written or a quoted string do not count
_GIT_VERBS = re.compile(r"(?:^|[;&|\n])\s*git\s+(commit|push)\b")
_HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\b", re.DOTALL)
_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
_PASTE = re.compile(r"</?pasted_content[^>]*>")


def redact(text: str) -> str:
    text = _PREFIXED.sub("[redacted]", text)
    text = _BEARER.sub("Bearer [redacted]", text)
    text = _ASSIGNED.sub(lambda m: m.group(1) + "[redacted]", text)

    def long_token(m: re.Match[str]) -> str:
        t = m.group(0)
        mixed = re.search(r"[A-Za-z]", t) and re.search(r"\d", t)
        is_hex = re.fullmatch(r"[0-9a-fA-F]+", t)  # commit hashes are fine
        return "[redacted]" if mixed and not is_hex else t

    return _LONG.sub(long_token, text)


def user_name(env: dict[str, str] | None = None, git_name: str | None = None) -> str:
    """`reejay`, `abhinav`, or a safe lower-case form of whatever git (or $USER) says."""
    env = os.environ if env is None else env
    raw = env.get("AGENT_BUILDER_USER") or git_name or env.get("USER") or "unknown"
    low = raw.lower()
    if "abhinav" in low or "abhi" in low:
        return "abhinav"
    if "reej" in low:
        return "reejay"
    return re.sub(r"[^a-z0-9]+", "-", low).strip("-") or "unknown"


def _git(args: list[str], cwd: str, *, strip: bool = True) -> str:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() if strip else out.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def changed_files(root: str) -> list[str]:
    """Files that changed since the last time this ran in this clone, however Claude changed them (Edit, a shell
    command, a script). Remembers the working tree between turns in the clone's own git directory (never committed).
    The first run only records the starting point. The work log itself is excluded."""
    state_file = _git(["rev-parse", "--git-path", "worklog-state.json"], root)
    if not state_file:
        return []  # not a git repository
    state_path = Path(root) / state_file

    def signature(path: str) -> list[int] | None:
        try:
            st = (Path(root) / path).stat()
        except OSError:
            return None  # deleted
        return [st.st_mtime_ns, st.st_size]

    entries = _git(["status", "--porcelain", "-uall", "-z"], root, strip=False).split(
        "\0"
    )
    current: dict[str, list[int] | None] = {}
    skip_next = False
    for entry in entries:
        if skip_next:
            skip_next = False
        elif len(entry) > 3:
            current[entry[3:]] = signature(entry[3:])
            skip_next = entry[0] in "RC"  # the next entry is the old name
    head = _git(["rev-parse", "HEAD"], root)
    try:
        previous = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        previous = None
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"head": head, "files": current}), encoding="utf-8"
    )
    if not isinstance(previous, dict):
        return []
    changed = {
        p for p, sig in current.items() if previous.get("files", {}).get(p) != sig
    }
    if previous.get("head") and head and previous["head"] != head:
        changed |= set(
            _git(
                ["diff", "--name-only", f"{previous['head']}..{head}"], root
            ).splitlines()
        )
    return sorted(p for p in changed if not p.startswith(f"{LOG_DIR}/"))


def _text_of(message: dict[str, Any]) -> str | None:
    """The human-written text of a user message, or None when it is only tool output or system noise."""
    content = message.get("content")
    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        parts = [
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ]
    else:
        return None
    text = _PASTE.sub("", _REMINDER.sub("", "\n".join(parts))).strip()
    return text or None


def _records(path: Path):  # type: ignore[no-untyped-def]
    """Yield transcript records, reading from the END in growing windows so a huge transcript stays cheap."""
    size = path.stat().st_size
    window = 2 * 1024 * 1024
    while True:
        start = max(0, size - window)
        with path.open("rb") as f:
            f.seek(start)
            data = f.read().decode("utf-8", errors="replace")
        lines = data.split("\n")
        if start > 0:
            lines = lines[1:]  # the first line may be cut in half
        records = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        yield records, start == 0
        if start == 0:
            return
        window *= 4


def last_turn(path: Path) -> dict[str, Any] | None:
    """The most recent real user prompt and everything Claude did after it."""
    for records, whole_file in _records(path):
        for i in range(len(records) - 1, -1, -1):
            r = records[i]
            if r.get("type") != "user" or r.get("isMeta") or r.get("isSidechain"):
                continue
            prompt = _text_of(r.get("message") or {})
            if prompt is None:
                continue
            return _summarise(r, prompt, records[i + 1 :])
        if whole_file:
            return None
    return None


def _summarise(
    user_record: dict[str, Any], prompt: str, after: list[dict[str, Any]]
) -> dict[str, Any]:
    files: list[str] = []
    actions: list[str] = []
    answer = ""
    for r in after:
        if r.get("type") != "assistant" or r.get("isSidechain"):
            continue
        for block in (r.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text", "").strip():
                answer = block["text"].strip()
            elif block.get("type") == "tool_use":
                name, args = block.get("name", ""), block.get("input") or {}
                if name in _EDIT_TOOLS and (
                    p := args.get("file_path") or args.get("notebook_path")
                ):
                    files.append(str(p))
                elif name == "Bash":
                    for verb in _GIT_VERBS.findall(
                        _HEREDOC.sub("", str(args.get("command", "")))
                    ):
                        actions.append("committed" if verb == "commit" else "pushed")
                elif name == "Skill" and args.get("skill"):
                    actions.append(f"ran skill {args['skill']}")
    return {
        "uuid": user_record.get("uuid", ""),
        "session": str(user_record.get("sessionId", ""))[:8],
        "prompt": prompt,
        "files": files,
        "actions": actions,
        "answer": answer,
    }


def render(turn: dict[str, Any], root: str, when: datetime) -> str:
    def rel(p: str) -> str:
        try:
            return str(Path(p).resolve().relative_to(Path(root).resolve()))
        except ValueError:
            return p

    files = sorted({rel(p) for p in turn["files"]})
    prompt = " ".join(redact(turn["prompt"]).split())
    answer = " ".join(redact(turn["answer"]).split())
    lines = [f"## {when:%H:%M}", f"<!-- turn:{turn['uuid']} -->"]
    lines.append(
        f"**Asked:** {prompt[:PROMPT_CHARS]}{'…' if len(prompt) > PROMPT_CHARS else ''}"
    )
    if files:
        shown = ", ".join(f"`{p}`" for p in files[:MAX_FILES])
        lines.append(
            f"**Files changed:** {shown}{f' (+{len(files) - MAX_FILES} more)' if len(files) > MAX_FILES else ''}"
        )
    actions = list(dict.fromkeys(turn["actions"]))
    if actions:
        lines.append(f"**Also:** {', '.join(actions)}")
    if answer:
        lines.append(
            f"**Claude replied:** {answer[:ANSWER_CHARS]}{'…' if len(answer) > ANSWER_CHARS else ''}"
        )
    return "\n".join(lines) + "\n\n"


def append_entry(
    root: str, user: str, turn: dict[str, Any], when: datetime
) -> Path | None:
    target = Path(root) / LOG_DIR / f"{when:%Y-%m-%d}" / f"{user}.md"
    marker = f"<!-- turn:{turn['uuid']} -->"
    if (
        target.exists()
        and turn["uuid"]
        and marker in target.read_text(encoding="utf-8")
    ):
        return None  # this turn is already logged (the hook can fire twice)
    target.parent.mkdir(parents=True, exist_ok=True)
    header = ""
    if not target.exists():
        header = (
            f"# Work log: {when:%Y-%m-%d} ({user})\n\n"
            "Written automatically by `.claude/hooks/log_work.py` after each Claude turn. Do not edit by hand.\n\n"
        )
    with target.open("a", encoding="utf-8") as f:
        f.write(header + render(turn, root, when))
    return target


def run(hook_input: dict[str, Any], now: datetime | None = None) -> Path | None:
    transcript = hook_input.get("transcript_path")
    cwd = hook_input.get("cwd") or os.getcwd()
    if not transcript or not Path(transcript).is_file():
        return None
    root = _git(["rev-parse", "--show-toplevel"], cwd) or cwd
    turn = last_turn(Path(transcript))
    if turn is None:
        return None
    turn["files"] = [
        *turn["files"],
        *(str(Path(root) / p) for p in changed_files(root)),
    ]
    user = user_name(git_name=_git(["config", "user.name"], root))
    return append_entry(root, user, turn, now or datetime.now())


def main() -> int:
    with contextlib.suppress(
        Exception
    ):  # a logging hook must never break or slow the user's session
        run(json.load(sys.stdin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
