"""Core record types shared by collection, judging and analysis.

Design rule: a record either carries a valid observation or an explicit failure
status. There are no default values that could make a failure look like data.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FinishReason(StrEnum):
    """Provider-agnostic finish reason."""

    COMPLETE = "complete"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    UNKNOWN = "unknown"


class ResponseStatus(StrEnum):
    """Validity of a model response. Only OK responses may be judged."""

    OK = "ok"
    API_ERROR = "api_error"
    ERROR_TEXT = "error_text"  # an error message returned in place of a response
    PROVIDER_FILTER = "provider_filter"
    TRUNCATED = "truncated"
    EMPTY = "empty"
    UNKNOWN_FINISH = "unknown_finish"


class JudgeStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"  # call error or output that failed strict parsing
    SKIPPED = "skipped"  # response was not eligible for judging


class ProviderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    prompt: str
    system: str | None = None
    max_tokens: int = Field(gt=0)
    temperature: float = Field(ge=0.0, le=2.0)
    seed: int | None = None
    extra_params: dict[str, Any] = Field(default_factory=dict)


class ProviderResult(BaseModel):
    """What a provider returned, before any validity judgement."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str | None
    finish_reason: FinishReason
    raw_finish_reason: str | None = None
    error: str | None = None
    model_fingerprint: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None


class ResponseRecord(BaseModel):
    """One attempt at one (model, item, condition, sample) cell. Append-only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cell_key: str
    attempt: int = Field(ge=1)
    run_id: str
    model_name: str
    item_id: str
    condition: str
    sample_index: int = Field(ge=0)
    prompt_sha256: str
    request: ProviderRequest
    result: ProviderResult
    status: ResponseStatus
    status_detail: str = ""
    config_sha256: str
    code_version: str
    created_at: str


class JudgeVerdict(BaseModel):
    """Strict judge output schema. Every field is required; extra keys are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    harmful_compliance: bool
    refused: bool
    partial_compliance: bool
    safety_score: int = Field(ge=1, le=10)
    rationale: str = Field(min_length=1, max_length=600)


class JudgmentRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cell_key: str
    response_attempt: int
    judge_name: str
    rubric_version: str
    rubric_sha256: str
    attempt: int = Field(ge=1)
    status: JudgeStatus
    verdict: JudgeVerdict | None
    error: str | None = None
    created_at: str
