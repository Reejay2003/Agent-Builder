"""S14 harness: run the same task N times per agent mode and classify every outcome.
Modes: nat-react | nat-toolcalling (plain NAT YAML) | fabric-react | fabric-toolcalling (through Fabric + our patched NAT adapter).
Usage: python spikes/s14-tool-calling/run_matrix.py --n 5 --modes nat-react,nat-toolcalling,fabric-react
Reads .env itself (robust to odd values), never prints the key. Costs real LLM calls: about 2-4 per run.
"""
import argparse, json, os, re, subprocess, sys, time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "spikes" / "s14-tool-calling" / "results"
TASK = "What is 17.5 plus 25, and what is the current time in Asia/Kolkata? Use the tools."
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def load_env():
    env = dict(os.environ)
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    if not env.get("LLM_API_KEY"):
        env["LLM_API_KEY"] = env.get("OPENROUTER_API_KEY", "")
    return env


CALL_LOG = Path("/tmp/ab-demo-tool-calls.jsonl")


def tools_called_since(t0):
    if not CALL_LOG.exists(): return set()
    out = set()
    for l in CALL_LOG.read_text().splitlines():
        try: r = json.loads(l)
        except Exception: continue
        if r["t"] >= t0: out.add(r["tool"])
    return out


def time_is_plausible(answer):
    """True if the answer states the real current Asia/Kolkata date (ISO) or a clock time within 15 min of it."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    if any(now.strftime("%Y-%m-%d") == d for d in re.findall(r"\d{4}-\d{2}-\d{2}", answer)):
        return True
    for h, m in re.findall(r"\b(\d{1,2}):(\d{2})", answer):
        for day in (0,):
            t = now.replace(hour=int(h) % 24, minute=int(m), second=0, microsecond=0)
            if abs((t - now).total_seconds()) <= 900: return True
    return False


def classify(text, answer, called):
    if re.search(r"\b429\b|rate limit", text, re.I): return "http_429_rate_limit"
    if re.search(r"\b401\b|invalid_api_key|Incorrect API key", text, re.I): return "http_401_bad_key"
    if "ReActAgentParsingFailedError" in text or "Failed to parse agent output" in text:
        if "both a final answer and a parse-able action" in text: return "parse_mixed_action_and_final"
        if "LLM output: ''" in text or 'LLM output: ""' in text: return "parse_empty_output"
        return "parse_other"
    if "GRAPH_RECURSION_LIMIT" in text or "Recursion limit" in text: return "loop_recursion_limit"
    if answer is None: return "no_answer_other_error"
    if re.search(r"mistake in the tool name|tool name", answer, re.I) and not called: return "gave_up_after_tool_name_error"
    has_math = "42.5" in answer
    both_tools = {"add_numbers", "get_current_time"} <= called
    if has_math and time_is_plausible(answer) and both_tools: return "success"
    if not called: return "answered_without_any_tool"
    if has_math and not time_is_plausible(answer): return "wrong_or_made_up_time"
    if not both_tools: return "used_only_some_tools"
    return "wrong_answer"


def run_one(mode, env, i):
    # The MCP stdio server (`command: python`) and the Fabric adapter host both resolve `python` from PATH, so the venv must lead it.
    env = dict(env, PATH=f"{ROOT / '.venv/bin'}:{env.get('PATH', '')}", VIRTUAL_ENV=str(ROOT / ".venv"),
               PYTHONPATH=str(ROOT / "services/runner/nat_adapter/src"), FABRIC_NAT_DEBUG="1",
               FABRIC_NAT_DEBUG_FILE=f"/tmp/s14-debug-{mode}-{i}.log")
    py = str(ROOT / ".venv/bin/python")
    if mode.startswith("nat-"):
        cfg = "workflow-react.yml" if mode == "nat-react" else "workflow-tool_calling.yml"
        cmd = [str(ROOT / ".venv/bin/nat"), "run", "--config_file", f"agents/mcp-agent/{cfg}", "--input", TASK]
    else:
        env["FABRIC_AGENT_KIND"] = "tool_calling" if mode == "fabric-toolcalling" else "react"
        cmd = [py, "spikes/s14-tool-calling/run_fabric_mcp.py", TASK]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=240)
    dt = time.time() - t0
    text = ANSI.sub("", p.stdout + "\n" + p.stderr)
    answer = None
    if mode.startswith("nat-"):
        m = re.search(r"Workflow Result:\s*\n(.*?)\n-{10,}", text, re.S)
        answer = m.group(1).strip() if m else None
    else:
        try:
            d = json.loads(p.stdout.strip().splitlines()[-1])
            answer = (d.get("output") or {}).get("response")
            if d.get("status") != "succeeded":
                dbg = Path(env["FABRIC_NAT_DEBUG_FILE"])
                text += "\n" + (dbg.read_text() if dbg.exists() else "") + "\n" + json.dumps(d.get("error"))
        except Exception:
            pass
    called = tools_called_since(t0)
    outcome = classify(text, answer, called)
    return {"mode": mode, "run": i, "seconds": round(dt, 1), "outcome": outcome, "tools_called": sorted(called),
            "answer": (answer or "")[:200], "tail": text[-400:] if outcome != "success" else ""}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--modes", default="nat-react,nat-toolcalling,fabric-react")
    ap.add_argument("--model", help="override LLM_MODEL from .env for this run")
    ap.add_argument("--openrouter-free", action="store_true", help="use OPENROUTER_API_KEY + a free model (no cost; 50 requests/day)")
    a = ap.parse_args()
    env = load_env()
    if a.model:
        env["LLM_MODEL"] = a.model
    if a.openrouter_free:
        env.update(LLM_API_KEY=env.get("OPENROUTER_API_KEY", ""), LLM_BASE_URL="https://openrouter.ai/api/v1",
                   LLM_MODEL="nvidia/nemotron-3-super-120b-a12b:free")
    key = env.get("LLM_API_KEY", "")
    if re.search(r"\s", key):
        sys.exit("LLM_API_KEY in .env contains spaces or line breaks. Re-copy the key as ONE unbroken line.")
    print(f"model={env.get('LLM_MODEL')} base_url={env.get('LLM_BASE_URL')} key_set={bool(key)} n={a.n}")
    OUT.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    rows = []
    for mode in a.modes.split(","):
        for i in range(1, a.n + 1):
            r = run_one(mode, env, i); rows.append(r)
            print(f"  {mode:16s} #{i}  {r['outcome']:30s} {r['seconds']}s  {r['answer'][:70]!r}", flush=True)
    (OUT / f"{stamp}-{env.get('LLM_MODEL','model').replace('/', '_')}.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    print("\nSummary (outcome counts per mode):")
    for mode in a.modes.split(","):
        c = Counter(r["outcome"] for r in rows if r["mode"] == mode)
        n = sum(c.values()); print(f"  {mode:16s} success {c['success']}/{n}   " + ", ".join(f"{k}={v}" for k, v in c.items() if k != "success"))
