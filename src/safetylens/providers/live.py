"""Groq and Anthropic adapters. Disabled unless explicitly opted in.

These adapters have NOT been exercised against the real APIs in this repository;
tests cover them with stub clients only. Before any live run, the preflight
check (one call per model) must confirm that extra parameters are accepted and
that finish reasons are returned.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from safetylens.providers.base import require_live_opt_in
from safetylens.quality import normalise_finish_reason
from safetylens.records import FinishReason, ProviderRequest, ProviderResult


@dataclass
class GroqProvider:
    client: Any
    name: str = "groq"
    is_live: bool = True

    @classmethod
    def create(cls, *, allow_live: bool) -> GroqProvider:
        require_live_opt_in(allow_live)
        from groq import Groq  # optional dependency: pip install safetylens[live]

        return cls(client=Groq())

    def generate(self, request: ProviderRequest) -> ProviderResult:
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        kwargs: dict[str, Any] = {
            "model": request.model_id,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.seed is not None:
            kwargs["seed"] = request.seed
        kwargs.update(request.extra_params)
        start = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception as exc:  # recorded as API_ERROR, never as a response
            return ProviderResult(
                text=None,
                finish_reason=FinishReason.UNKNOWN,
                error=f"{type(exc).__name__}: {exc}"[:500],
            )
        choice = resp.choices[0]
        usage = getattr(resp, "usage", None)
        return ProviderResult(
            text=choice.message.content,
            finish_reason=normalise_finish_reason(choice.finish_reason),
            raw_finish_reason=choice.finish_reason,
            model_fingerprint=getattr(resp, "system_fingerprint", None),
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            latency_ms=(time.perf_counter() - start) * 1000,
        )


@dataclass
class AnthropicProvider:
    client: Any
    name: str = "anthropic"
    is_live: bool = True

    @classmethod
    def create(cls, *, allow_live: bool) -> AnthropicProvider:
        require_live_opt_in(allow_live)
        from anthropic import Anthropic  # optional dependency

        return cls(client=Anthropic())

    def generate(self, request: ProviderRequest) -> ProviderResult:
        kwargs: dict[str, Any] = {
            "model": request.model_id,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system:
            kwargs["system"] = request.system
        kwargs.update(request.extra_params)
        start = time.perf_counter()
        try:
            msg = self.client.messages.create(**kwargs)
        except Exception as exc:
            return ProviderResult(
                text=None,
                finish_reason=FinishReason.UNKNOWN,
                error=f"{type(exc).__name__}: {exc}"[:500],
            )
        text = "".join(
            getattr(block, "text", "")
            for block in msg.content
            if getattr(block, "type", None) == "text"
        )
        usage = getattr(msg, "usage", None)
        return ProviderResult(
            text=text,
            finish_reason=normalise_finish_reason(msg.stop_reason),
            raw_finish_reason=msg.stop_reason,
            model_fingerprint=getattr(msg, "model", None),
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            latency_ms=(time.perf_counter() - start) * 1000,
        )
