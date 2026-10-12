"""Varied task suite for the agent-type comparison. Every task has a deterministic check, the tools it REQUIRES, and
whether tools are FORBIDDEN (the question needs none). Tool use is proven by the MCP server's own call log, not by the answer text."""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def _nums(s):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(s).replace(",", ""))]


def has_num(*wanted, tol=0.011):
    return lambda a: all(any(abs(n - w) <= tol for n in _nums(a)) for w in wanted)


def has_text(*words):
    return lambda a: all(w.lower() in str(a).lower() for w in words)


def time_in(tz):
    """The answer states a clock time within 15 minutes of now in `tz` (24h or 12h with AM/PM)."""
    def check(a):
        now = datetime.now(ZoneInfo(tz))
        for h, m, ap in re.findall(r"\b(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?", str(a)):
            h = int(h); m = int(m)
            if ap:
                h = h % 12 + (12 if ap.lower() == "pm" else 0)
            if h > 23 or m > 59:
                continue
            t = now.replace(hour=h, minute=m, second=0, microsecond=0)
            for delta in (0, -1, 1):  # tolerate midnight wrap
                if abs((t + timedelta(days=delta) - now).total_seconds()) <= 900:
                    return True
        return False
    return check


def says_unknown_tz(a):
    a = str(a)
    return bool(re.search(r"unknown|invalid|fictional|not (a )?(real|valid|recogni[sz]ed|found|exist)|does(n't| not) (exist|have)|couldn't|could not|unable|isn't|no such|cannot|can't", a, re.I)) \
        and not re.search(r"\b\d{1,2}:\d{2}\b", a)


def T(id, cat, q, check, required=(), forbid=False):
    return dict(id=id, cat=cat, q=q, check=check, required=set(required), forbid=forbid)


TASKS = [
    # A. one tool, math (including awkward numbers)
    T("a1", "math", "What is 17.5 plus 25? Use the tools.", has_num(42.5), ["add_numbers"]),
    T("a2", "math", "Add -8.25 and 3.75. Use the tools.", has_num(-4.5), ["add_numbers"]),
    T("a3", "math", "What is 123456.789 plus 987654.321? Use the tools.", has_num(1111111.11), ["add_numbers"]),
    T("a4", "math", "What is 0.1 plus 0.2? Use the tools.", has_num(0.3), ["add_numbers"]),
    # B. one tool, text
    T("b1", "text", "How many words are in: 'the quick brown fox jumps over the lazy dog'? Use the tools.", has_num(9), ["count_words"]),
    T("b2", "text", "Count the words in: 'one'. Use the tools.", has_num(1), ["count_words"]),
    T("b3", "text", "How many words are in this sentence: 'agents   need reliable   tools'? Use the tools.", has_num(4), ["count_words"]),
    # C. time tool, different zones
    T("c1", "time", "What is the current time in Asia/Tokyo? Use the tools.", time_in("Asia/Tokyo"), ["get_current_time"]),
    T("c2", "time", "What time is it right now in America/New_York? Use the tools.", time_in("America/New_York"), ["get_current_time"]),
    T("c3", "time", "Tell me the current time in UTC. Use the tools.", time_in("UTC"), ["get_current_time"]),
    # D. several tools, including chained steps
    T("d1", "multi", "Add 17.5 and 25, and also tell me the current time in Asia/Kolkata. Use the tools.",
      lambda a: has_num(42.5)(a) and time_in("Asia/Kolkata")(a), ["add_numbers", "get_current_time"]),
    T("d2", "multi", "What is 2.5 plus 2.5, and how many words are in 'one two three'? Use the tools.", has_num(5, 3), ["add_numbers", "count_words"]),
    T("d3", "chain", "Count the words in 'agents need reliable tools', then add that count to 10. Use the tools.", has_num(14), ["count_words", "add_numbers"]),
    T("d4", "chain", "Add 3 and 4, then add 10 to that result. Use the tools.", has_num(17), ["add_numbers"]),
    # E. no tool needed: calling one is a failure
    T("e1", "no_tool", "What is the capital of France? Do not use tools.", has_text("paris"), forbid=True),
    T("e2", "no_tool", "Say hello in one short sentence.", lambda a: len(str(a).strip()) > 0, forbid=True),
    T("e3", "no_tool", "What is 2 plus 2? Answer from your own knowledge; do not use any tools.", has_num(4), forbid=True),
    # F. traps and edge cases
    T("f1", "trap", "What time is it in Atlantis/Lost_City? Use the tools.", says_unknown_tz),  # correct = say it is unknown; calling the tool first is fine too
    T("f2", "trap", "Add 1000000 and 2000000. Use the tools.", has_num(3000000, tol=1), ["add_numbers"]),
    T("f3", "trap", "Use the add_numbers tool to add 5 and 6.", has_num(11), ["add_numbers"]),
]
