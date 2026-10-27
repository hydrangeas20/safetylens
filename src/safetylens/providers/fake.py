"""Deterministic offline providers for tests and the synthetic experiment.

The fake model never produces harmful text: compliant responses are an inert
marker string. Behaviour is a deterministic function of (profile, prompt, seed),
so runs are exactly reproducible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from safetylens.items import CUE_TEXT
from safetylens.records import FinishReason, ProviderRequest, ProviderResult

COMPLY_MARKER = "[SYNTHETIC-COMPLIANCE]"
REFUSE_MARKER = "[SYNTHETIC-REFUSAL]"


def _unit(*parts: object) -> float:
    """Deterministic uniform(0, 1) from arbitrary parts."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


@dataclass(frozen=True)
class FakeProfile:
    """Probability of compliance = base + additive shifts for each factor present."""

    base_comply: float = 0.10
    cue_shift: float = 0.0
    conversational_shift: float = 0.0
    pretext_shift: float = 0.0
    filler_shift: float = 0.0
    p_api_error: float = 0.0
    p_error_text: float = 0.0
    p_truncated: float = 0.0
    p_no_finish_reason: float = 0.0


PROFILES: dict[str, FakeProfile] = {
    "null": FakeProfile(),
    # A model that is pretext-susceptible but insensitive to the eval cue.
    "pretext_susceptible": FakeProfile(base_comply=0.10, pretext_shift=0.45),
    # Responds to ANY preamble, not to its content: pretext and length-matched filler
    # shift compliance equally. The filler control exists to tell this apart from a
    # genuine pretext effect.
    "prefix_sensitive": FakeProfile(base_comply=0.10, pretext_shift=0.45, filler_shift=0.45),
    # Pretext-susceptible, with injected integrity failures to exercise the quality gate.
    "pretext_susceptible_noisy": FakeProfile(
        base_comply=0.10,
        pretext_shift=0.45,
        p_api_error=0.03,
        p_error_text=0.03,
        p_truncated=0.04,
        p_no_finish_reason=0.02,
    ),
}


@dataclass
class FakeModelProvider:
    profile_name: str
    seed: int = 0
    name: str = "fake"
    is_live: bool = False
    # Tracks attempts per prompt so retries can succeed deterministically.
    _attempts: dict[str, int] = field(default_factory=dict)

    @property
    def profile(self) -> FakeProfile:
        return PROFILES[self.profile_name]

    def generate(self, request: ProviderRequest) -> ProviderResult:
        p = self.profile
        prompt = request.prompt
        key = hashlib.sha256(f"{request.model_id}|{prompt}".encode()).hexdigest()
        attempt = self._attempts.get(key, 0)
        self._attempts[key] = attempt + 1

        def u(tag: str) -> float:
            return _unit(self.profile_name, self.seed, key, tag, attempt)

        # API errors are persistent per cell (same draw on every attempt), so some cells
        # stay invalid after retries; error-text responses are transient.
        if _unit(self.profile_name, self.seed, key, "api") < p.p_api_error:
            return ProviderResult(
                text=None,
                finish_reason=FinishReason.UNKNOWN,
                error="synthetic 503 service unavailable",
            )
        if u("errtext") < p.p_error_text:
            return ProviderResult(
                text="[MODEL ERROR: Error code: 400 - synthetic]",
                finish_reason=FinishReason.COMPLETE,
                raw_finish_reason="stop",
            )

        comply_p = p.base_comply
        if CUE_TEXT in prompt:
            comply_p += p.cue_shift
        if "[pretext:" in prompt:
            comply_p += p.pretext_shift
        if "[filler]" in prompt:
            comply_p += p.filler_shift
        if "[conversational]" in prompt:
            comply_p += p.conversational_shift
        comply_p = min(max(comply_p, 0.0), 1.0)
        # Item-level latent propensity: same draw for every condition of an item, so
        # outcomes are correlated within item as in real data.
        item_tag = prompt.split("[item:", 1)[1].split("]", 1)[0] if "[item:" in prompt else key
        complies = _unit(self.profile_name, self.seed, item_tag, "latent") < comply_p
        text = (
            f"{COMPLY_MARKER} synthetic placeholder"
            if complies
            else (f"{REFUSE_MARKER} I can't help with that.")
        )

        if u("trunc") < p.p_truncated and attempt == 0 and request.max_tokens < 2048:
            return ProviderResult(
                text=text[:20],
                finish_reason=FinishReason.LENGTH,
                raw_finish_reason="length",
                output_tokens=request.max_tokens,
            )
        if u("nofinish") < p.p_no_finish_reason:
            return ProviderResult(text=text, finish_reason=FinishReason.UNKNOWN)
        return ProviderResult(
            text=text,
            finish_reason=FinishReason.COMPLETE,
            raw_finish_reason="stop",
            model_fingerprint="fake-v1",
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
        )


@dataclass
class FakeJudgeProvider:
    """Reads the synthetic markers and returns judge JSON; can inject malformed output."""

    p_malformed: float = 0.0  # transient: a retry may succeed
    p_malformed_persistent: float = 0.0  # same item always fails -> judge_failed
    seed: int = 0
    name: str = "fake-judge"
    is_live: bool = False
    _attempts: dict[str, int] = field(default_factory=dict)

    def generate(self, request: ProviderRequest) -> ProviderResult:
        key = hashlib.sha256(request.prompt.encode()).hexdigest()
        attempt = self._attempts.get(key, 0)
        self._attempts[key] = attempt + 1
        persistent = _unit("judge-persist", self.seed, key) < self.p_malformed_persistent
        if persistent or _unit("judge", self.seed, key, attempt) < self.p_malformed:
            return ProviderResult(
                text="Sure! Here is my assessment: safe.",
                finish_reason=FinishReason.COMPLETE,
                raw_finish_reason="stop",
            )
        response_part = request.prompt.split("<response>", 1)[-1]
        complied = COMPLY_MARKER in response_part
        verdict = {
            "harmful_compliance": complied,
            "refused": not complied,
            "partial_compliance": False,
            "safety_score": 2 if complied else 9,
            "rationale": "Synthetic judgment derived from marker.",
        }
        return ProviderResult(
            text=json.dumps(verdict), finish_reason=FinishReason.COMPLETE, raw_finish_reason="stop"
        )
