"""Turns the key-passing probe output into PASS/FAIL and an exit code (0 = every property holds).
Usage: python key_verdict.py results/key-with-provider.txt results/key-no-provider.txt  [reads the real key from ../../.env]"""
import re
import sys

with_p, without_p = (open(p, errors="replace").read() for p in sys.argv[1:3])
real = ""
for line in open("../../.env"):
    if line.startswith("LLM_API_KEY="):
        real = line.split("=", 1)[1].strip().strip('"').strip("'")

def line_of(text, tag):
    return next((ln for ln in text.splitlines() if ln.startswith(tag)), "")

checks = [
    ("sandbox env holds a placeholder, not the real key", "present=True" in line_of(with_p, "K1")
     and "looks_like_real_key=False" in line_of(with_p, "K1")),
    ("python reaches api.openai.com and the proxy injects the key (HTTP 200)", line_of(with_p, "K2").endswith(": 200")),
    ("curl reaches api.openai.com (HTTP 200)", line_of(with_p, "K3").endswith(": 200")),
    ("the key is not sent to another host (curl)", "BLOCKED" in line_of(with_p, "K4")),
    ("the key is not sent to another host (python)", "BLOCKED" in line_of(with_p, "K5")),
    ("the real key appears nowhere the sandbox can read it (env, /proc, files)", bool(real) and real not in with_p),
    ("sandbox sees only a loopback interface (no NIC)", line_of(with_p, "K9").endswith("lo")),
    ("without the provider there is no key variable", "OPENAI_API_KEY set: no" in without_p),
    ("without the provider api.openai.com is unreachable", "http=000" in without_p),
]
bad = 0
for name, ok in checks:
    print(("PASS  " if ok else "FAIL  ") + name)
    bad += not ok
print("note: K6 (bash started BY the allowed python is OPEN) is expected: children inherit the parent's access; see README")
sys.exit(1 if bad else 0)
