# Instructions for AI assistants working in this repo
- Read [COMPLETED.md](COMPLETED.md) first, then the relevant part of [PLAN.md](PLAN.md). Do not redo finished spikes; respect the Decisions and Gotchas lists.
- Update COMPLETED.md when you finish something (date, evidence, lesson). Tag facts [verified] only if you ran or read them in the primary source.
- Never print, log or commit API keys. Secrets live only in the git-ignored `.env`.
- Setup and checks: `make setup`, `make check`; run `make fabric-doctor` before LLM-spending runs. The free OpenRouter tier is 50 requests a day, so do not loop on failing LLM runs; log raw responses once.
- Python 3.11 to 3.13 only. Pin versions; no `--prerelease` for the core set.
- Ask before: deleting data, running `curl | sh` installers, pushing, or anything that spends money.
