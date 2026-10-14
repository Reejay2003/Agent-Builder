from pathlib import Path

import pytest

EXAMPLES = Path(__file__).parent.parent / "examples" / "specs"


@pytest.fixture
def example_paths() -> list[Path]:
    paths = sorted(EXAMPLES.glob("*.agent.yaml"))
    assert paths, "no example specs found"
    return paths


def minimal() -> dict:
    return {"name": "demo", "model": {"provider": "openai", "model": "gpt-4.1-mini"}}


GOLDEN = Path(__file__).parent / "golden"


def assert_golden(name: str, text: str) -> None:
    """Compare `text` with tests/golden/<name>. Regenerate on purpose with UPDATE_GOLDEN=1 and review the diff."""
    import os

    path = GOLDEN / name
    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert path.exists(), f"missing golden file {path}; generate with UPDATE_GOLDEN=1"
    assert path.read_text(encoding="utf-8") == text, (
        f"{name} changed; if intended, rerun with UPDATE_GOLDEN=1 and review the diff"
    )
