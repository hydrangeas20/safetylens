from __future__ import annotations

import pytest

from safetylens.quality import (
    classify,
    ends_with_terminal_punctuation,
    is_judgeable,
    looks_like_error_text,
    normalise_finish_reason,
)
from safetylens.records import FinishReason, ProviderResult, ResponseStatus

# Exact response string recorded for all 42 archived Qwen3-32B rows.
HISTORICAL_QWEN_ERROR = (
    "[MODEL ERROR: Error code: 400 - {'error': {'message': \"property 'thinking' is "
    "unsupported\", 'type': 'invalid_request_error'}}]"
)


def result(
    text: str | None = "A complete answer.",
    finish: FinishReason = FinishReason.COMPLETE,
    error: str | None = None,
    raw: str | None = "stop",
) -> ProviderResult:
    return ProviderResult(text=text, finish_reason=finish, error=error, raw_finish_reason=raw)


@pytest.mark.parametrize(
    ("res", "status"),
    [
        (result(), ResponseStatus.OK),
        (result(error="timeout"), ResponseStatus.API_ERROR),
        (result(text=HISTORICAL_QWEN_ERROR), ResponseStatus.ERROR_TEXT),
        (
            result(finish=FinishReason.CONTENT_FILTER, raw="content_filter"),
            ResponseStatus.PROVIDER_FILTER,
        ),
        (result(text="   "), ResponseStatus.EMPTY),
        (result(text=None), ResponseStatus.EMPTY),
        (result(finish=FinishReason.LENGTH, raw="length"), ResponseStatus.TRUNCATED),
        (result(finish=FinishReason.UNKNOWN, raw=None), ResponseStatus.UNKNOWN_FINISH),
    ],
)
def test_classification(res: ProviderResult, status: ResponseStatus) -> None:
    assert classify(res)[0] is status


def test_historical_qwen_string_is_rejected_before_judging() -> None:
    status, detail = classify(result(text=HISTORICAL_QWEN_ERROR))
    assert status is ResponseStatus.ERROR_TEXT
    assert not is_judgeable(status)
    assert "thinking" in detail


def test_error_beats_truncation_and_text() -> None:
    res = result(text="partial", finish=FinishReason.LENGTH, error="boom")
    assert classify(res)[0] is ResponseStatus.API_ERROR


def test_unknown_finish_allowed_only_when_opted_out() -> None:
    res = result(finish=FinishReason.UNKNOWN, raw=None)
    assert classify(res, require_finish_reason=False)[0] is ResponseStatus.OK


@pytest.mark.parametrize("status", [s for s in ResponseStatus if s is not ResponseStatus.OK])
def test_only_ok_is_judgeable(status: ResponseStatus) -> None:
    assert not is_judgeable(status)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("stop", FinishReason.COMPLETE),
        ("end_turn", FinishReason.COMPLETE),
        ("length", FinishReason.LENGTH),
        ("max_tokens", FinishReason.LENGTH),
        ("content_filter", FinishReason.CONTENT_FILTER),
        ("refusal", FinishReason.CONTENT_FILTER),
        ("STOP ", FinishReason.COMPLETE),
        ("weird", FinishReason.UNKNOWN),
        (None, FinishReason.UNKNOWN),
    ],
)
def test_finish_normalisation(raw: str | None, expected: FinishReason) -> None:
    assert normalise_finish_reason(raw) is expected


@pytest.mark.parametrize(
    "text",
    ["[MODEL ERROR: x]", "[api error] 500", "Error code: 429 - rate limited", '{"error": "bad"}'],
)
def test_error_text_patterns(text: str) -> None:
    assert looks_like_error_text(text)


@pytest.mark.parametrize("text", ["I can't help with that.", "The error in your code is...", None])
def test_not_error_text(text: str | None) -> None:
    assert not looks_like_error_text(text)


def test_terminal_punctuation() -> None:
    assert ends_with_terminal_punctuation("Done.  ")
    assert ends_with_terminal_punctuation("**Note**")
    assert not ends_with_terminal_punctuation("and then the")
    assert not ends_with_terminal_punctuation("   ")
