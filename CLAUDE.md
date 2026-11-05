# Instructions for AI assistants working in this repo
- Read [COMPLETED.md](COMPLETED.md) first, then the relevant part of [PLAN.md](PLAN.md). Do not redo finished spikes; respect the Decisions and Gotchas lists.
- Update COMPLETED.md when you finish something (date, evidence, lesson). Tag facts [verified] only if you ran or read them in the primary source.
- Never print, log or commit API keys. Secrets live only in the git-ignored `.env`.
- Setup and checks: `make setup`, `make check`; run `make fabric-doctor` before LLM-spending runs. The free OpenRouter tier is 50 requests a day, so do not loop on failing LLM runs; log raw responses once.
- Python 3.11 to 3.13 only. Pin versions; no `--prerelease` for the core set.
- **Always run `/ponytail-review` on code you wrote or changed before you call the work done, and give the owner its findings (numbered, with the verdict).** Do this every time, not only when asked. It is read-only; fix only what the owner approves.
- **Daily work log is automatic.** A Claude Code `Stop` hook (`.claude/settings.json` -> `.claude/hooks/log_work.py`) appends every turn (what was asked, files changed, commits/pushes, the start of the answer) to `work log/<date>/<user>.md` (`reejay` or `abhinav`, from `git config user.name`; override with `AGENT_BUILDER_USER`). Commit those files, do not edit them by hand. Key-shaped text is redacted before writing. Test: `python -m pytest .claude/hooks`.
- Ask before: deleting data, running `curl | sh` installers, pushing, or anything that spends money.
