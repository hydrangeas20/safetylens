from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from safetylens.config import ExperimentConfig, JudgeSpec, ModelSpec, SamplingSpec
from safetylens.providers.base import LiveCallsDisabledError
from safetylens.providers.fake import FakeModelProvider
from safetylens.records import FinishReason, ProviderRequest, ProviderResult, ResponseRecord
from safetylens.records import ResponseStatus as S
from safetylens.runner import collect
from safetylens.storage import JsonlStore
from safetylens.synthetic import synthetic_items


def config(design: str = "compact", **sampling: object) -> ExperimentConfig:
    return ExperimentConfig(
        experiment="t",
        items_path="x",
        design=design,  # type: ignore[arg-type]
        models=[ModelSpec(name="m", provider="fake", model_id="m")],
        judge=JudgeSpec(name="j", provider="fake", model_id="j"),
        sampling=SamplingSpec(**sampling),  # type: ignore[arg-type]
    )


@dataclass
class Scripted:
    """Returns scripted results in order, recording requests."""

    results: list[ProviderResult]
    name: str = "scripted"
    is_live: bool = False
    requests: list[ProviderRequest] = field(default_factory=list)

    def generate(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        return self.results[min(len(self.requests) - 1, len(self.results) - 1)]


OK = ProviderResult(text="fine.", finish_reason=FinishReason.COMPLETE, raw_finish_reason="stop")
TRUNC = ProviderResult(text="cut", finish_reason=FinishReason.LENGTH, raw_finish_reason="length")
ERR = ProviderResult(text="[MODEL ERROR: 400]", finish_reason=FinishReason.COMPLETE)


def store(tmp_path: Path) -> JsonlStore[ResponseRecord]:
    return JsonlStore(tmp_path / "r.jsonl", ResponseRecord)


def one_item_config() -> tuple[ExperimentConfig, list]:  # type: ignore[type-arg]
    return config(design="compact"), synthetic_items(n_a=1, n_c=0)


def test_truncation_retried_with_larger_budget(tmp_path: Path) -> None:
    cfg, items = config(max_tokens=256, truncation_retry_max_tokens=2048), synthetic_items(1, 0)
    prov = Scripted([TRUNC, OK] * 5)
    st = store(tmp_path)
    collect(cfg, items[:1], {"m": prov}, st, run_id="r", clock=lambda: "t")
    first_cell = [r for r in st.all() if r.condition == st.all()[0].condition]
    assert [r.status for r in first_cell] == [S.TRUNCATED, S.OK]
    assert [r.request.max_tokens for r in first_cell] == [256, 2048]


def test_still_truncated_after_retry_stays_truncated(tmp_path: Path) -> None:
    cfg = config(max_tokens=256, truncation_retry_max_tokens=2048, max_attempts=5)
    st = store(tmp_path)
    counts = collect(
        cfg, synthetic_items(1, 0), {"m": Scripted([TRUNC])}, st, run_id="r", clock=lambda: "t"
    )
    assert counts == {"final_truncated": 5}
    assert all(
        len([r for r in st.all() if r.cell_key == k]) == 2 for k in {r.cell_key for r in st.all()}
    )


def test_error_text_never_becomes_ok(tmp_path: Path) -> None:
    st = store(tmp_path)
    counts = collect(
        config(max_attempts=3),
        synthetic_items(1, 0),
        {"m": Scripted([ERR])},
        st,
        run_id="r",
        clock=lambda: "t",
    )
    assert counts == {"final_error_text": 5}
    assert all(r.status is S.ERROR_TEXT for r in st.all()) and len(st.all()) == 15


def test_resume_appends_nothing_when_complete(tmp_path: Path) -> None:
    cfg, items = config(design="full"), synthetic_items(3, 1)
    st = store(tmp_path)
    prov = FakeModelProvider("pretext_susceptible_noisy", seed=1)
    collect(cfg, items, {"m": prov}, st, run_id="r", clock=lambda: "t")
    n_lines = len(st.path.read_text().splitlines())
    finals_before = {r.cell_key: r.status for r in st.all()}
    counts = collect(cfg, items, {"m": prov}, st, run_id="r", clock=lambda: "t")
    # Terminal cells are skipped; only non-terminal cells (if any) get new attempts.
    non_terminal = [k for k, s in finals_before.items() if s not in (S.OK, S.PROVIDER_FILTER)]
    assert counts.get("skipped_complete", 0) == 48 - len(non_terminal)
    assert len(st.path.read_text().splitlines()) >= n_lines


def test_records_are_append_only_and_carry_provenance(tmp_path: Path) -> None:
    st = store(tmp_path)
    cfg = config()
    collect(
        cfg,
        synthetic_items(1, 0),
        {"m": Scripted([OK])},
        st,
        run_id="run-9",
        clock=lambda: "2026-01-01",
    )
    before = st.path.read_text()
    collect(
        cfg,
        synthetic_items(2, 0),
        {"m": Scripted([OK])},
        st,
        run_id="run-9",
        clock=lambda: "2026-01-01",
    )
    assert st.path.read_text().startswith(before)
    rec = st.all()[0]
    assert rec.config_sha256 == cfg.sha256() and rec.run_id == "run-9"
    assert rec.result.raw_finish_reason == "stop" and len(rec.prompt_sha256) == 64


def test_live_provider_blocked(tmp_path: Path) -> None:
    prov = Scripted([OK], is_live=True)
    with pytest.raises(LiveCallsDisabledError):
        collect(config(), synthetic_items(1, 0), {"m": prov}, store(tmp_path), run_id="r")
    assert prov.requests == []


def test_corrupt_store_line_raises(tmp_path: Path) -> None:
    st = store(tmp_path)
    st.path.write_text('{"not": "a record"}\n')
    with pytest.raises(ValueError, match="corrupt record"):
        st.all()


def test_store_type_check(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        store(tmp_path).append(OK)  # type: ignore[arg-type]
