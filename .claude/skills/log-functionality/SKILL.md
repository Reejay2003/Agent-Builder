---
name: log-functionality
description: >
  Records a finished feature in FUNCTIONALITIES.md, the owner's interview-prep
  list of what the platform can do and how each part works. Use right after a
  feature, fix with user-visible behaviour, or runner/tool/endpoint is finished
  and tested, when the owner says "log this", "add to the functionality list",
  "update FUNCTIONALITIES", or /log-functionality. Logs only what PLAN.md does
  not already describe (or how the build differed from it). Do this together
  with the COMPLETED.md update, not instead of it.
---

`FUNCTIONALITIES.md` (repo root) is read by the owner before interviews. It must let them explain each
feature out loud: what it is, why it exists, how it works step by step, what was decided, what it cannot do.
It is NOT a changelog (that is COMPLETED.md) and NOT marketing.

## When to run
- A feature is finished and its tests pass: a runner, endpoint, command, tool, compiler step, safety rule.
- A fix that changes behaviour the owner could be asked about (a new guard, a changed default).
- Skip: refactors, renames, docs-only changes, work that is not finished or not tested.

## What belongs here (the plan filter)
`FUNCTIONALITIES.md` holds ONLY what [PLAN.md](../../../PLAN.md) (the phases and design sections) does not
already describe explicitly. Things the plan covers are explained there; repeating them here clutters this file.
Before writing anything, search PLAN.md for the feature's name and key terms (`grep -n -i`), and decide:
- **The plan describes it and we built it as described** → do NOT add it. Say so to the owner in one line
  ("covered by PLAN §x, not logged").
- **The plan describes it but we built it differently or went beyond it** (a simpler design, an extra safety
  guard, a bug found on a real system, a trade-off the plan did not foresee) → add an entry that covers ONLY
  the difference: start "What it is" with the plan reference (`PLAN §4.4.1`) and write just what changed and why.
  Skip the parts the plan already explains.
- **The plan does not mention it** (a helper, a process or tooling piece, a decision made while building) → add
  a normal full entry.
When unsure whether the plan covers it, read the plan section and judge by behaviour, not by the name. If still
unsure, ask the owner in one line instead of guessing.

## Steps
1. Read the code and the tests for the feature. Every claim in the entry must come from code you read or a test
   you ran. Never write from memory of the conversation alone. If you did not verify something, say so in
   **Not verified**.
2. Apply the plan filter above first. Then open `FUNCTIONALITIES.md`. If the feature already has an entry, UPDATE it (and its date); do not add a
   second one. Otherwise take the next free number `F<n>` and add the entry at the end of its area section
   (create the area if it fits none), then add one line to the index table at the top.
3. Write the entry with exactly this template, in plain English, short sentences, a term explained the first
   time it appears:

   ```
   ### F<n>. <Feature name>
   - **Added:** <YYYY-MM-DD> · **Status:** done | partial (say what is missing)
   - **What it is:** <one or two sentences a non-expert understands>
   - **Why we built it:** <the problem it solves, ideally from a real failure or decision we hit>
   - **How it works:** <numbered steps of the real flow, naming the real functions/files>
   - **Decisions and trade-offs:** <what we chose, what we rejected, and why>
   - **Limits:** <what it cannot do or does not do yet>
   - **Where:** <file paths>
   - **Proof:** <which tests, which real run; mark [verified] only for things actually run or read>
   - **Not verified:** <anything not tested live or against the real service>
   - **Interview angle:** <2 likely questions with a short honest answer each>
   ```
4. Add a line to the `Recent additions` list at the top (newest first): date, F-number, one sentence.
5. Never put API keys, tokens, emails or private paths in the file. Do not claim a result that was not
   measured (no invented percentages or timings); copy numbers only from COMPLETED.md or a run you did.
6. Tell the owner in one or two lines which entry you added or updated. Do not commit unless asked.
