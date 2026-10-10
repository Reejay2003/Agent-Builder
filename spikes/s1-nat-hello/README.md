# S1: NAT hello world (passed 2026-10-10)

NeMo Agent Toolkit 1.9.0 + OpenRouter (OpenAI-compatible, free model) + one tool, no NVIDIA key.

Setup: `uv venv --python 3.12 && uv pip install packaging "nvidia-nat[langchain]"`
Run: `./run.sh "your question"` (reads OPENROUTER_API_KEY from the repo-root .env)

Findings:
- Plain `nvidia-nat` is not enough; `nvidia-nat[langchain]` is needed.
- `_type: openai` with `base_url` pointing at OpenRouter works for BYOK.
- Model: nvidia/nemotron-3-super-120b-a12b:free. ReAct agent called the tool and answered correctly.
