"""Response validity classification.

This is the gate that would have caught the historical Qwen3-32B failure, where
every "response" was an API error string that was then scored by the judge.
"""

from __future__ import annotations

import re

from safetylens.records import FinishReason, ProviderResult, ResponseStatus

# Error strings that have been observed (or are typical) when a client wraps an
# exception into the response text instead of raising.
_ERROR_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*\[\s*MODEL ERROR", re.IGNORECASE),
    re.compile(r"^\s*\[\s*(API|PROVIDER|REQUEST) ERROR", re.IGNORECASE),
    re.compile(r"^\s*Error code:\s*[45]\d\d\b", re.IGNORECASE),
    re.compile(r"^\s*\{\s*['\"]error['\"]\s*:", re.IGNORECASE),
)

_FINISH_MAP: dict[str, FinishReason] = {
    # OpenAI-compatible (Groq)
    "stop": FinishReason.COMPLETE,
    "length": FinishReason.LENGTH,
    "content_filter": FinishReason.CONTENT_FILTER,
    # Anthropic
    "end_turn": FinishReason.COMPLETE,
    "stop_sequence": FinishReason.COMPLETE,
    "max_tokens": FinishReason.LENGTH,
    "refusal": FinishReason.CONTENT_FILTER,
}


def normalise_finish_reason(raw: str | None) -> FinishReason:
    if raw is None:
        return FinishReason.UNKNOWN
    return _FINISH_MAP.get(raw.strip().lower(), FinishReason.UNKNOWN)


def looks_like_error_text(text: str | None) -> bool:
    if text is None:
        return False
    return any(p.search(text) for p in _ERROR_TEXT_PATTERNS)


def classify(
    result: ProviderResult, *, require_finish_reason: bool = True
) -> tuple[ResponseStatus, str]:
    """Return (status, detail). Order matters: errors beat everything else."""
    if result.error is not None:
        return ResponseStatus.API_ERROR, result.error[:200]
    if looks_like_error_text(result.text):
        assert result.text is not None
        return ResponseStatus.ERROR_TEXT, result.text[:200]
    if result.finish_reason is FinishReason.CONTENT_FILTER:
        return ResponseStatus.PROVIDER_FILTER, result.raw_finish_reason or ""
    if result.text is None or not result.text.strip():
        return ResponseStatus.EMPTY, ""
    if result.finish_reason is FinishReason.LENGTH:
        return ResponseStatus.TRUNCATED, result.raw_finish_reason or "length"
    if result.finish_reason is FinishReason.UNKNOWN and require_finish_reason:
        return ResponseStatus.UNKNOWN_FINISH, result.raw_finish_reason or "missing"
    return ResponseStatus.OK, ""


def is_judgeable(status: ResponseStatus) -> bool:
    """Only complete, error-free responses are sent to the judge."""
    return status is ResponseStatus.OK


_TERMINAL = (".", "!", "?", ")", '"', "'", "”", "’", "`", "*")


def ends_with_terminal_punctuation(text: str) -> bool:
    """Heuristic used only for historical data that lacks finish reasons."""
    stripped = text.rstrip()
    return bool(stripped) and stripped.endswith(_TERMINAL)
