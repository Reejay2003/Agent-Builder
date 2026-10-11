"""Summarize NAT eval ATIF output: per item, was the answer right, which tools ran, did a tool call error out.
Usage: python spikes/s4-relay-eval/summarize.py spikes/s4-relay-eval/out/react [...]"""
import json, re, sys
from collections import Counter

def nums(s): return {round(float(x), 6) for x in re.findall(r"-?\d+(?:\.\d+)?", str(s).replace(",", ""))}

def summarize(d):
    items = json.load(open(f"{d}/workflow_output_atif.json"))
    traj_scores = {}
    try:
        for it in json.load(open(f"{d}/trajectory_output.json"))["eval_output_items"]: traj_scores[str(it["id"])] = it["score"]
    except Exception: pass
    c = Counter(); rows = []
    for it in items:
        steps = it["trajectory"]["steps"]
        calls, errs = [], 0
        for s in steps:
            for tc in (s.get("tool_calls") or []):
                n = tc.get("function_name") or tc.get("name") or ""
                if "__" in n: calls.append(n.split("__", 1)[1])  # real MCP tools only (prefix demo_tools__); skips LangGraph internals
            for ob in ((s.get("observation") or {}).get("results") or []):
                if re.search(r"not (a valid|found)|unknown tool|error", str(ob.get("content", "")), re.I): errs += 1
        expected = str(it["expected_output_obj"]); got = str(it["output_obj"] or "")
        ok = nums(expected) <= nums(got)   # every expected number appears in the answer
        wanted = {"q1": {"add_numbers"}, "q2": {"count_words"}, "q3": {"add_numbers"}, "q4": {"count_words"}, "q5": {"add_numbers", "count_words"}}.get(str(it["item_id"]).split("_")[0], set())
        extra = sorted(set(calls) - wanted)
        kind = ("correct" if ok and calls and not extra else "correct_but_extra_tool_calls" if ok and calls
                else "correct_without_tool" if ok else ("tool_error_then_wrong" if errs else "wrong_or_empty"))
        c[kind] += 1
        rows.append((it["item_id"], kind, sorted(set(calls)), "tool_errors=%d" % errs, got[:80]))
    return c, rows

for d in sys.argv[1:]:
    c, rows = summarize(d)
    print(f"== {d}: {sum(c.values())} runs  " + ", ".join(f"{k}={v}" for k, v in c.items()))
    for r in rows:
        if r[1] != "correct": print("   ", r)
