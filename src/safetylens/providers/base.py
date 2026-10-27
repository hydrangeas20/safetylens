"""Provider interface and the live-call guard."""

from __future__ import annotations

import os
from typing import Protocol

from safetylens.records import ProviderRequest, ProviderResult

LIVE_ENV_VAR = "SAFETYLENS_ALLOW_LIVE"


class LiveCallsDisabledError(RuntimeError):
    """Raised when a live (paid) provider is used without explicit opt-in."""


class Provider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def is_live(self) -> bool: ...

    def generate(self, request: ProviderRequest) -> ProviderResult: ...


def require_live_opt_in(config_allows_live: bool) -> None:
    """Live calls need BOTH config.allow_live and SAFETYLENS_ALLOW_LIVE=1."""
    if not config_allows_live:
        raise LiveCallsDisabledError("live providers are disabled: config.allow_live is false")
    if os.environ.get(LIVE_ENV_VAR) != "1":
        raise LiveCallsDisabledError(f"live providers are disabled: set {LIVE_ENV_VAR}=1 to opt in")
