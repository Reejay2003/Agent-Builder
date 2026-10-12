"""Big comparison: models x agent setups x varied tasks x reps, in parallel, with per-run MCP call logs as proof of tool use.
  python spikes/s14-tool-calling/run_suite.py --models gpt-4.1-nano,gpt-4.1-mini --reps 2 --workers 4 --tag run1
Modes: nat-react | nat-toolcalling | fabric-react | fabric-toolcalling.  Costs real LLM calls (about 2-4 per run).
Resumable: re-running with the same --tag skips jobs already in results/suite-<tag>.jsonl.  `--summary-only` prints tables."""
import argparse, json, os, re, subprocess, sys, tempfile, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tasks import TASKS  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")
MODES = ["nat-react", "nat-toolcalling", "fabric-react", "fabric-toolcalling"]


def load_env():
    env = dict(os.environ)
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); env[k.strip()] = v.strip().strip('"').strip("'")
    if not env.get("LLM_API_KEY"):
        env["LLM_API_KEY"] = env.get("OPENROUTER_API_KEY", "")
    return env


def tools_called(log):
    p = Path(log)
    out = []
    if p.exists():
        for l in p.read_text().splitlines():
            try: out.append(json.loads(l)["tool"])
            except Exception: pass
    return out


def run_job(job, base_env):
    model, mode, task, rep = job["model"], job["mode"], job["task"], job["rep"]
    tmp = Path(tempfile.mkdtemp(prefix="abs-"))
    log = tmp / "tools.jsonl"
    env = dict(base_env, LLM_MODEL=model, PATH=f"{ROOT / '.venv/bin'}:{base_env.get('PATH', '')}", VIRTUAL_ENV=str(ROOT / ".venv"),
               PYTHONPATH=str(ROOT / "spikes/s2-fabric-nat/src"), FABRIC_NAT_DEBUG="1", FABRIC_NAT_DEBUG_FILE=str(tmp / "debug.log"),
               AB_TOOL_LOG_PATH=str(log))
    if mode.startswith("nat-"):
        tpl = (ROOT / "agents/mcp-agent" / ("workflow-react.yml" if mode == "nat-react" else "workflow-tool_calling.yml")).read_text()
        cfg = tmp / "wf.yml"
        cfg.write_text(tpl.replace('args: ["packages/mcp-tools/demo_server.py"]', f'args: ["packages/mcp-tools/demo_server.py", "--log", "{log}"]'))
        cmd = [str(ROOT / ".venv/bin/nat"), "run", "--config_file", str(cfg), "--input", task["q"]]
    else:
        env["FABRIC_AGENT_KIND"] = "tool_calling" if mode == "fabric-toolcalling" else "react"
        cmd = [str(ROOT / ".venv/bin/python"), "spikes/s14-tool-calling/run_fabric_mcp.py", task["q"]]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        out, err = p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        out, err = "", "TIMEOUT"
    dt = time.time() - t0
    text = ANSI.sub("", out + "\n" + err)
    answer = None
    if mode.startswith("nat-"):
        m = re.search(r"Workflow Result:\s*\n(.*?)\n-{10,}", text, re.S)
        answer = m.group(1).strip() if m else None
    else:
        try:
            d = json.loads(out.strip().splitlines()[-1])
            answer = (d.get("output") or {}).get("response")
            if d.get("status") != "succeeded":
                dbg = tmp / "debug.log"
                text += "\n" + (dbg.read_text() if dbg.exists() else "") + json.dumps(d.get("error"))
        except Exception:
            pass
    calls = tools_called(log)
    called = set(calls)
    rec = dict(model=model, mode=mode, task=task["id"], cat=task["cat"], rep=rep, seconds=round(dt, 1), calls=calls,
               answer=(answer or "")[:240])
    if re.search(r"\b429\b|rate limit", text, re.I) and answer is None: rec["outcome"] = "http_429"
    elif re.search(r"\b401\b|invalid_api_key", text) and answer is None: rec["outcome"] = "http_401"
    elif "TIMEOUT" in text: rec["outcome"] = "timeout"
    elif "GRAPH_RECURSION_LIMIT" in text or "Recursion limit" in text: rec["outcome"] = "loop_recursion_limit"
    elif "ReActAgentParsingFailedError" in text or "Failed to parse agent output" in text: rec["outcome"] = "parse_error"
    elif answer is None: rec["outcome"] = "no_answer_other_error"; rec["tail"] = text[-300:]
    else:
        ok = bool(task["check"](answer)); req = task["required"]; forbid = task["forbid"]
        if forbid:
            rec["outcome"] = "success" if ok and not called else "called_tool_when_not_needed" if called else "wrong_answer"
        elif ok and req <= called: rec["outcome"] = "success"
        elif ok: rec["outcome"] = "right_answer_without_required_tool"
        elif not (req <= called): rec["outcome"] = "wrong_and_skipped_required_tool"
        else: rec["outcome"] = "wrong_answer"
        extra = (called - req) if not forbid else called
        rec["clean"] = rec["outcome"] == "success" and not extra
        rec["extra_tools"] = sorted(extra)
    return rec


def summarize(path):
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    print(f"\n{len(rows)} runs in {path}\n")
    by = defaultdict(list)
    for r in rows: by[(r["model"], r["mode"])].append(r)
    print(f"{'model':16s} {'agent setup':20s} {'n':>4s} {'success':>8s} {'clean*':>7s} {'avg s':>6s}  failures")
    for (m, mode), rs in sorted(by.items()):
        n = len(rs); s = sum(r["outcome"] == "success" for r in rs); c = sum(bool(r.get("clean")) for r in rs)
        fails = Counter(r["outcome"] for r in rs if r["outcome"] != "success")
        print(f"{m:16s} {mode:20s} {n:4d} {100*s/n:7.1f}% {100*c/n:6.1f}% {sum(r['seconds'] for r in rs)/n:6.1f}  " + ", ".join(f"{k}={v}" for k, v in fails.most_common()))
    print("\nsuccess % by category (model / setup):")
    cats = sorted({r["cat"] for r in rows})
    print(f"{'':37s}" + "".join(f"{c:>9s}" for c in cats))
    for (m, mode), rs in sorted(by.items()):
        cells = []
        for c in cats:
            x = [r for r in rs if r["cat"] == c]; cells.append(f"{100*sum(r['outcome']=='success' for r in x)/len(x):8.0f}%" if x else "       -")
        print(f"{m:16s} {mode:20s}" + "".join(cells))
    print("\n* clean = success AND no unrequested tool calls.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gpt-4.1-nano,gpt-4.1-mini")
    ap.add_argument("--modes", default=",".join(MODES))
    ap.add_argument("--tasks", default="", help="comma list of task ids (default all)")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--tag", default="run1")
    ap.add_argument("--summary-only", action="store_true")
    a = ap.parse_args()
    out = HERE / "results" / f"suite-{a.tag}.jsonl"; out.parent.mkdir(exist_ok=True)
    if a.summary_only: summarize(out); sys.exit()
    env = load_env()
    if re.search(r"\s", env.get("LLM_API_KEY", "")) or not env.get("LLM_API_KEY"): sys.exit("LLM_API_KEY missing or contains spaces")
    tasks = [t for t in TASKS if not a.tasks or t["id"] in a.tasks.split(",")]
    done = set()
    if out.exists():
        for l in out.read_text().splitlines():
            if l.strip():
                r = json.loads(l); done.add((r["model"], r["mode"], r["task"], r["rep"]))
    jobs = [dict(model=m, mode=mode, task=t, rep=r) for m in a.models.split(",") for mode in a.modes.split(",") for t in tasks for r in range(a.reps)
            if (m, mode, t["id"], r) not in done]
    print(f"{len(jobs)} jobs to run ({len(done)} already done), {a.workers} workers, base_url={env.get('LLM_BASE_URL')}", flush=True)
    t0 = time.time(); n = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex, out.open("a") as f:
        futs = [ex.submit(run_job, j, env) for j in jobs]
        for fu in as_completed(futs):
            rec = fu.result(); f.write(json.dumps(rec) + "\n"); f.flush(); n += 1
            if n % 10 == 0 or n == len(jobs):
                print(f"  {n}/{len(jobs)} done, {time.time()-t0:.0f}s elapsed", flush=True)
    summarize(out)
