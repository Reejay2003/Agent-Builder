"""Tests for the work-log hook. Run: python -m pytest .claude/hooks/test_log_work.py"""

import io
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import log_work as w

WHEN = datetime(2026, 11, 5, 14, 32)
SECRET = "sk-proj-Zx9Qp2Lm7Vb4Nc1RZx9Qp2Lm7Vb4Nc1R"


def line(kind, content, **extra):
    return json.dumps(
        {
            "type": kind,
            "uuid": extra.pop("uuid", "u"),
            "message": {"content": content},
            **extra,
        }
    )


def transcript(tmp_path, records, name="t.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(records) + "\n")
    return p


def test_redaction_removes_key_shaped_values_and_keeps_ordinary_text():
    text = (
        f"use {SECRET} and nvapi-AbCdEf1234567890abcd, OPENAI_API_KEY=abc123, password: 'hunter2 hunter2', "
        "Authorization: Bearer abcdefgh12345678, token Zx9Qp2Lm7Vb4Nc1RZx9Qp2Lm7Vb4Nc1R9 ok"
    )
    out = w.redact(text)
    for leaked in (
        SECRET,
        "nvapi-AbCdEf",
        "abc123",
        "hunter2",
        "abcdefgh12345678",
        "Zx9Qp2Lm7Vb4",
    ):
        assert leaked not in out, leaked
    assert "use [redacted]" in out and out.endswith("ok")
    ordinary = "commit fa36e65d0c1b2a3f4e5d6c7b8a9f0e1d2c3b4a59 changed packages/sdk/src/agentbuilder/server/app.py"
    assert w.redact(ordinary) == ordinary  # hashes and paths are not secrets


def test_user_names_map_both_contributors_and_fall_back_safely():
    assert w.user_name(env={}, git_name="Reejay2003") == "reejay"
    assert w.user_name(env={}, git_name="Abhinav Bhakat") == "abhinav"
    assert w.user_name(env={}, git_name="Abhinav72313") == "abhinav"
    assert (
        w.user_name(env={"AGENT_BUILDER_USER": "Someone Else"}, git_name="Reejay2003")
        == "someone-else"
    )
    assert (
        w.user_name(env={"USER": "../../etc"}, git_name=None) == "etc"
    )  # never a path


def test_the_last_real_prompt_is_found_and_tool_noise_is_skipped(tmp_path):
    t = transcript(
        tmp_path,
        [
            line("user", "old question", uuid="old"),
            line(
                "user",
                "make the thing <system-reminder>hidden</system-reminder>",
                uuid="u1",
                sessionId="abcdef123456",
            ),
            line(
                "assistant",
                [
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {"file_path": "/r/a/b.py"},
                    }
                ],
            ),
            line("user", [{"type": "tool_result", "content": "ok"}]),
            line("user", "meta noise", isMeta=True),
            line(
                "assistant",
                [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "git commit -m x && git push"},
                    }
                ],
            ),
            line(
                "assistant",
                [
                    {
                        "type": "tool_use",
                        "name": "Write",
                        "input": {"file_path": "/r/c.md"},
                    }
                ],
                isSidechain=True,
            ),
            line("assistant", [{"type": "text", "text": "Done. I changed b.py."}]),
        ],
    )
    turn = w.last_turn(t)
    assert (
        turn["uuid"] == "u1"
        and turn["prompt"] == "make the thing"
        and turn["session"] == "abcdef12"
    )
    assert turn["files"] == ["/r/a/b.py"] and turn["actions"] == ["committed", "pushed"]
    assert turn["answer"] == "Done. I changed b.py."


def test_entry_is_written_to_work_date_user_with_a_header_redacted_and_not_duplicated(
    tmp_path,
):
    root = tmp_path / "repo"
    t = transcript(
        tmp_path,
        [
            line("user", f"here is my key {SECRET} please test", uuid="turn-1"),
            line(
                "assistant",
                [
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {"file_path": str(root / "packages/x.py")},
                    }
                ],
            ),
            line("assistant", [{"type": "text", "text": "I tested it."}]),
        ],
    )
    first = w.append_entry(str(root), "reejay", w.last_turn(t), WHEN)
    assert first == root / "work log" / "2026-11-05" / "reejay.md"
    body = first.read_text()
    assert body.startswith("# Work log: 2026-11-05 (reejay)") and "## 14:32" in body
    assert (
        "`packages/x.py`" in body
        and "I tested it." in body
        and SECRET not in body
        and "[redacted]" in body
    )
    assert (
        w.append_entry(str(root), "reejay", w.last_turn(t), WHEN) is None
    )  # same turn: not logged twice
    assert first.read_text().count("turn:turn-1") == 1


def test_two_people_get_two_files_and_a_second_turn_appends(tmp_path):
    for name, uid in (("reejay", "a"), ("abhinav", "b"), ("reejay", "c")):
        t = transcript(
            tmp_path, [line("user", f"task {uid}", uuid=uid)], name=f"{uid}.jsonl"
        )
        w.append_entry(str(tmp_path), name, w.last_turn(t), WHEN)
    day = tmp_path / "work log" / "2026-11-05"
    assert sorted(p.name for p in day.iterdir()) == ["abhinav.md", "reejay.md"]
    assert (day / "reejay.md").read_text().count("## 14:32") == 2 and (
        day / "reejay.md"
    ).read_text().count("# Work log") == 1


def test_a_huge_transcript_is_still_read_from_the_end(tmp_path):
    filler = [
        line("assistant", [{"type": "text", "text": "x" * 4000}]) for _ in range(1500)
    ]  # about 6 MB after the prompt
    t = transcript(tmp_path, [line("user", "the real question", uuid="big"), *filler])
    assert w.last_turn(t)["prompt"] == "the real question"


def test_the_hook_never_fails_on_bad_input(tmp_path, monkeypatch):
    assert w.run({}) is None
    assert w.run({"transcript_path": str(tmp_path / "missing.jsonl")}) is None
    empty = tmp_path / "e.jsonl"
    empty.write_text("not json\n{}\n")
    assert w.run({"transcript_path": str(empty), "cwd": str(tmp_path)}) is None
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(empty.read_text())
    )  # garbage on stdin
    assert w.main() == 0


def test_words_inside_a_written_file_do_not_count_as_git_actions(tmp_path):
    script = "cat > x.py <<'EOF'\nrun(('git commit', 'committed'), 'git push')\nEOF"
    real = "cd repo && git add -A && git commit -q -m x\ngit push"
    t = transcript(
        tmp_path,
        [
            line("user", "do it", uuid="g"),
            line(
                "assistant",
                [{"type": "tool_use", "name": "Bash", "input": {"command": script}}],
            ),
        ],
    )
    assert w.last_turn(t)["actions"] == []
    t = transcript(
        tmp_path,
        [
            line("user", "do it", uuid="g"),
            line(
                "assistant",
                [{"type": "tool_use", "name": "Bash", "input": {"command": real}}],
            ),
        ],
        name="real.jsonl",
    )
    assert w.last_turn(t)["actions"] == ["committed", "pushed"]


def _repo(tmp_path):
    import subprocess

    def g(*args):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    g("init", "-q")
    (tmp_path / "a.py").write_text("1")
    g("add", "-A")
    g("commit", "-qm", "first")
    return g


def test_changed_files_sees_shell_edits_new_files_and_commits_but_not_the_work_log(
    tmp_path,
):
    g = _repo(tmp_path)
    root = str(tmp_path)
    assert w.changed_files(root) == []  # first run only records the starting point
    (tmp_path / "a.py").write_text("changed by a shell command")
    (tmp_path / "b.py").write_text("new")
    (tmp_path / "work log" / "2026-11-05").mkdir(parents=True)
    (tmp_path / "work log" / "2026-11-05" / "reejay.md").write_text("log")
    assert w.changed_files(root) == ["a.py", "b.py"]
    assert w.changed_files(root) == []  # nothing new since the last turn
    (tmp_path / "c.py").write_text("committed in the same turn")
    g("add", "-A")
    g("commit", "-qm", "second")
    assert "c.py" in w.changed_files(
        root
    )  # a file that was changed and committed is still reported


def test_changed_files_outside_git_is_empty_and_does_not_crash(tmp_path):
    assert w.changed_files(str(tmp_path)) == []
