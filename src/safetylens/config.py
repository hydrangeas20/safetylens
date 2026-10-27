"""Experiment configuration schema (YAML -> validated pydantic models)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProviderName = Literal["fake", "replay", "groq", "anthropic"]
LIVE_PROVIDERS: frozenset[str] = frozenset({"groq", "anthropic"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelSpec(_Strict):
    name: str = Field(min_length=1)
    provider: ProviderName
    model_id: str = Field(min_length=1)
    # Provider-specific request parameters. Must be verified against provider docs
    # and by the preflight check; an unsupported parameter is what invalidated the
    # historical Qwen3-32B run.
    extra_params: dict[str, Any] = Field(default_factory=dict)
    # Fake provider behaviour (only used when provider == "fake").
    fake_profile: str | None = None


class JudgeSpec(_Strict):
    name: str = Field(min_length=1)
    provider: ProviderName
    model_id: str = Field(min_length=1)
    rubric_version: str = "v1-draft"
    max_tokens: int = Field(default=400, gt=0)
    max_attempts: int = Field(default=3, ge=1, le=10)


class SamplingSpec(_Strict):
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    samples_per_cell: int = Field(default=1, ge=1, le=50)
    seed: int = 0
    max_tokens: int = Field(default=1024, gt=0)
    truncation_retry_max_tokens: int | None = Field(default=4096, gt=0)
    max_attempts: int = Field(default=3, ge=1, le=10)
    require_finish_reason: bool = True


class ExperimentConfig(_Strict):
    experiment: str = Field(min_length=1)
    items_path: str
    design: Literal["full", "compact"]
    models: list[ModelSpec] = Field(min_length=1)
    judge: JudgeSpec
    sampling: SamplingSpec = SamplingSpec()
    # Live calls require BOTH this flag and SAFETYLENS_ALLOW_LIVE=1 at runtime.
    allow_live: bool = False
    budget_usd_cap: float | None = Field(default=None, gt=0)
    output_dir: str = "runs"

    @field_validator("models")
    @classmethod
    def _unique_names(cls, v: list[ModelSpec]) -> list[ModelSpec]:
        names = [m.name for m in v]
        if len(names) != len(set(names)):
            raise ValueError("model names must be unique")
        return v

    @model_validator(mode="after")
    def _live_requires_budget(self) -> ExperimentConfig:
        uses_live = any(m.provider in LIVE_PROVIDERS for m in self.models) or (
            self.judge.provider in LIVE_PROVIDERS
        )
        if uses_live and self.allow_live and self.budget_usd_cap is None:
            raise ValueError("live providers require budget_usd_cap")
        return self

    def uses_live_providers(self) -> bool:
        return any(m.provider in LIVE_PROVIDERS for m in self.models) or (
            self.judge.provider in LIVE_PROVIDERS
        )

    def sha256(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()


def load_config(path: Path) -> ExperimentConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ExperimentConfig.model_validate(data)
