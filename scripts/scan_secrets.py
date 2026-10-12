#!/usr/bin/env python3
"""Fail if a staged/listed file contains something shaped like an API key. Used by pre-commit; works offline.
Usage: python scripts/scan_secrets.py FILE [FILE...]   (exit 1 and print file:line when something matches)"""
import re
import sys
from pathlib import Path

PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),  # OpenAI, OpenRouter, Anthropic-style
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),  # GitHub token
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),  # Slack
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),  # Google API key
]
# Intentional fake keys used to test the secret checks themselves.
ALLOW = ("packages/sdk/tests/", "scripts/scan_secrets.py", "packages/sdk/src/agentbuilder/spec/models.py")


def main(files: list[str]) -> int:
    bad = 0
    for name in files:
        if any(a in name.replace("\\", "/") for a in ALLOW):
            continue
        try:
            text = Path(name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(p.search(line) for p in PATTERNS):
                print(f"{name}:{lineno}: looks like an API key (value hidden)")
                bad = 1
    return bad


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
