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
