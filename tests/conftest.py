from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(autouse=True)
def _no_live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never inherit a live opt-in or real credentials from the environment."""
    for var in ("SAFETYLENS_ALLOW_LIVE", "GROQ_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
