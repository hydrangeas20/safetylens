"""Synthetic end-to-end experiment: proves the pipeline works with no network.

Items are inert placeholders ("SYNTHETIC REQUEST 007"), never real harmful
requests. Three deterministic fake models have KNOWN ground truth:

* fake-null     : no effects at all.
* fake-pretext  : pretext content raises compliance; filler and cue do nothing. Also
                  injects API errors, error-text responses, truncation and missing
                  finish reasons to exercise the validity gate.
* fake-prefix   : any preamble (filler or pretext) raises compliance equally, so the
                  pretext-vs-filler contrast must come out null while the
                  filler-vs-none control comes out positive.

The fake judge injects malformed outputs, some persistently. The test suite checks
that invalid observations are excluded and that the analysis recovers the ground
truth. Nothing here is an empirical finding about any real model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from safetylens.analysis.experiment import analyse_experiment, render_report
from safetylens.config import ExperimentConfig, JudgeSpec, ModelSpec, SamplingSpec
from safetylens.items import Item, load_items
from safetylens.judge import judge_responses
from safetylens.providers.base import Provider
from safetylens.providers.fake import FakeJudgeProvider, FakeModelProvider
from safetylens.providers.replay import RecordingProvider, ReplayProvider
from safetylens.records import JudgmentRecord, ResponseRecord
from safetylens.runner import collect
from safetylens.storage import JsonlStore

FIXED_CLOCK = "2026-01-01T00:00:00+00:00"

SYNTHETIC_PREAMBLE = """\
> [!WARNING]
> **SYNTHETIC DATA: NOT RESEARCH RESULTS.** Every number below comes from deterministic
> fake models with effects and failures injected by design (`safetylens.synthetic`). It
> demonstrates that the pipeline excludes invalid observations and recovers known ground
> truth. It says nothing about any real language model.

## Ground truth injected into the fake models

| Fake model | Injected behaviour | What a correct analysis should show |
|---|---|---|
| `fake-null` | No effects | No contrast significant |
| `fake-pretext` | Pretext content raises compliance; filler and cue do nothing. \
Injected API errors, error-text responses, truncation and missing finish reasons | \
Pretext-vs-filler contrasts positive and significant; invalid cells excluded and counted |
| `fake-prefix` | Any preamble (filler or pretext) raises compliance equally; the \
evaluation cue is not treated as a preamble | `filler_vs_none` control positive; \
pretext-vs-filler contrasts **not** significant; `cue_explicit_vs_filler` negative |

The fake judge also returns malformed output for some cells (transiently and \
persistently); those cells appear as `judge_failed` and are excluded, never counted as \
refusals. Each fake model draws one latent propensity per item, so an item either \
responds to a factor or does not; the confidence intervals reflect sampling of items."""


def synthetic_items(n_a: int = 40, n_c: int = 10) -> list[Item]:
    items: list[Item] = []
    for i in range(n_a + n_c):
        tier = "A" if i < n_a else "C"
        iid = f"syn-{tier}-{i:03d}"
        core = f"SYNTHETIC REQUEST {i:03d} [item:{iid}]"
        items.append(
            Item(
                id=iid,
                tier=tier,
                category="synthetic",
                source="synthetic",
                core_request=core,
                terse=core,
                conversational=f"[conversational] Hi, could you help me with this? {core}",
                pretexts={
                    "filler": "[filler] The weather today is mild.",
                    "fiction": "[pretext:fiction] I am writing a story.",
                    "professional": "[pretext:professional] I work in this field.",
                },
                compliance_appropriate="never" if tier == "A" else "always",
            )
        )
    return items


def write_items(items: list[Item], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(i.model_dump_json() + "\n" for i in items), encoding="utf-8")


def synthetic_config(items_path: Path, design: str = "full") -> ExperimentConfig:
    return ExperimentConfig(
        experiment="synthetic-e2e",
        items_path=str(items_path),
        design=design,
        models=[
            ModelSpec(name="fake-null", provider="fake", model_id="fake-null", fake_profile="null"),
            ModelSpec(
                name="fake-pretext",
                provider="fake",
                model_id="fake-pretext",
                fake_profile="pretext_susceptible_noisy",
            ),
            ModelSpec(
                name="fake-prefix",
                provider="fake",
                model_id="fake-prefix",
                fake_profile="prefix_sensitive",
            ),
        ],
        judge=JudgeSpec(name="fake-judge", provider="fake", model_id="fake-judge"),
        sampling=SamplingSpec(max_tokens=1024),
    )


@dataclass
class RunPaths:
    root: Path

    @property
    def responses(self) -> Path:
        return self.root / "responses.jsonl"

    @property
    def judgments(self) -> Path:
        return self.root / "judgments.jsonl"

    @property
    def model_cassette(self) -> Path:
        return self.root / "cassette_models.jsonl"

    @property
    def judge_cassette(self) -> Path:
        return self.root / "cassette_judge.jsonl"

    @property
    def results(self) -> Path:
        return self.root / "results.json"

    @property
    def report(self) -> Path:
        return self.root / "report.md"


def run_pipeline(
    config: ExperimentConfig,
    items: list[Item],
    model_providers: dict[str, Provider],
    judge_provider: Provider,
    paths: RunPaths,
    *,
    seed: int = 0,
) -> dict[str, Any]:
    clock = lambda: FIXED_CLOCK  # noqa: E731 - deterministic provenance for synthetic runs
    responses: JsonlStore[ResponseRecord] = JsonlStore(paths.responses, ResponseRecord)
    judgments: JsonlStore[JudgmentRecord] = JsonlStore(paths.judgments, JudgmentRecord)
    collect_counts = collect(
        config, items, model_providers, responses, run_id="synthetic", clock=clock
    )
    judge_counts = judge_responses(
        responses.all(), {i.id: i for i in items}, config.judge, judge_provider, judgments, clock
    )
    result = analyse_experiment(
        responses.all(),
        judgments.all(),
        items,
        config.design,
        [m.name for m in config.models],
        seed=seed,
    )
    result["pipeline_counts"] = {"collect": collect_counts, "judge": judge_counts}
    paths.results.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths.report.write_text(
        render_report(result, "SafetyLens synthetic demonstration", preamble=SYNTHETIC_PREAMBLE),
        encoding="utf-8",
    )
    return result


def run_synthetic(out_dir: Path, *, design: str = "full", record: bool = True) -> dict[str, Any]:
    paths = RunPaths(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    items_path = out_dir / "items.jsonl"
    write_items(synthetic_items(), items_path)
    items = load_items(items_path)
    config = synthetic_config(items_path, design)
    models: dict[str, Provider] = {}
    for m in config.models:
        inner = FakeModelProvider(profile_name=m.fake_profile or "null", seed=1)
        models[m.name] = RecordingProvider(inner, paths.model_cassette) if record else inner
    judge_inner = FakeJudgeProvider(p_malformed=0.05, p_malformed_persistent=0.02, seed=2)
    judge: Provider = (
        RecordingProvider(judge_inner, paths.judge_cassette) if record else (judge_inner)
    )
    return run_pipeline(config, items, models, judge, paths)


def replay_synthetic(source_dir: Path, out_dir: Path, *, design: str = "full") -> dict[str, Any]:
    """Re-run the pipeline from recorded cassettes only (strict replay)."""
    src = RunPaths(source_dir)
    paths = RunPaths(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    items = load_items(source_dir / "items.jsonl")
    config = synthetic_config(source_dir / "items.jsonl", design)
    model_replay = ReplayProvider(src.model_cassette)
    models: dict[str, Provider] = {m.name: model_replay for m in config.models}
    return run_pipeline(config, items, models, ReplayProvider(src.judge_cassette), paths)


@dataclass(frozen=True)
class DemoResult:
    results: dict[str, Any]
    replay_identical: bool
    report_path: Path


def run_demo(out_dir: Path, *, design: str = "full") -> DemoResult:
    """Record a synthetic run, replay it strictly from cassettes, and compare."""
    import shutil

    if out_dir.exists():
        shutil.rmtree(out_dir)
    recorded = run_synthetic(out_dir / "recorded", design=design)
    replayed = replay_synthetic(out_dir / "recorded", out_dir / "replayed", design=design)
    a = {k: v for k, v in recorded.items() if k != "pipeline_counts"}
    b = {k: v for k, v in replayed.items() if k != "pipeline_counts"}
    report_a = (out_dir / "recorded" / "report.md").read_text(encoding="utf-8")
    report_b = (out_dir / "replayed" / "report.md").read_text(encoding="utf-8")
    return DemoResult(recorded, a == b and report_a == report_b, out_dir / "recorded" / "report.md")
