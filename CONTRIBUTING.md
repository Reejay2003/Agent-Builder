# Contributing

## Before you start
1. Read [COMPLETED.md](COMPLETED.md). Do not redo a finished spike, and check **Gotchas** and **Decisions** first.
2. Pick a task from **Next up**, write your GitHub handle in `Owner`, set it to `in progress` (small PR or issue comment), so two people do not do the same thing.
3. Set up with `make setup && make up && make check` ([README](README.md)).

## Working rules
- **One task per branch and PR.** Branch names: `s4-relay-atif`, `fix/check-env-linux`, `docs/plan-wizard`.
- **Update COMPLETED.md in the same PR.** Done item with date + evidence, new gotchas, any changed decision (new row, do not edit old ones).
- **Spikes live in `spikes/<id>-<name>/`** with a `README.md` containing: the question, how to run it, the result (pass, partial, fail), and what surprised you. A failed spike is a valid result; write it down.
- **Pin versions.** NVIDIA's pieces are 0.x. Add new dependencies to `requirements.txt` with exact versions, then run `uv pip compile requirements.txt --universal --python-version 3.12 -o requirements.lock` and commit both. Do not use `--prerelease` for the core set.
- **Free and open source only** for default paths. Anything paid or licence-gated must be an optional provider (PLAN section 3).
- **Tag claims** in docs: **[verified]** (you ran or read it in the primary source) or **[unverified]**.
- **Test from a clean copy** before saying setup works: clone to a new folder and run `make setup && make check`.
- Do not change PLAN.md architecture silently; add an entry to its section 0 explaining the change and why.

## Secrets and safety
- Use your **own** API keys. `.env` is git-ignored; never paste keys into issues, PRs, chat logs or files.
- Before pushing: `git diff --cached | grep -i -E "sk-|api[_-]?key|secret|token"` should show nothing sensitive.
- If a key leaks, revoke it at the provider immediately; removing it from git history is not enough.
- Run unfamiliar install scripts only after reading them (the OpenShell installer installs a background service).

## Commits and PRs
Short imperative subject (`S4: wire Relay ATIF export`), a body explaining why. PR description: what changed, how you tested it, what COMPLETED.md entry you added.

## Using Claude Code or another AI assistant
Point it at COMPLETED.md and PLAN.md first (see [CLAUDE.md](CLAUDE.md)). Verify its claims; this repo has already had a wrong version number and a wrong "it works" caught by checking.
