"""Offline end-to-end: synthetic collection -> judging -> analysis -> strict replay."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from safetylens.cli import main
from safetylens.providers.replay import CassetteMissError
from safetylens.synthetic import replay_synthetic, run_synthetic

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def synthetic_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    out = tmp_path_factory.mktemp("syn")
    return out, run_synthetic(out / "recorded")


def test_injected_failures_are_excluded_and_counted(synthetic_run) -> None:  # type: ignore[no-untyped-def]
    _, res = synthetic_run
    integ = res["integrity"]["fake-pretext"]
    assert integ["valid"] + sum(integ["invalid_by_reason"].values()) == integ["cells"] == 600
    assert integ["invalid_by_reason"].get("response_api_error", 0) > 0
    assert res["pipeline_counts"]["judge"]["judge_failed"] > 0
    for contrast in res["models"]["fake-pretext"]["primary_tier_A"].values():
        assert contrast["n_items"] + sum(contrast["excluded_items"].values()) == 40


def test_injected_effect_recovered_and_null_not_flagged(synthetic_run) -> None:  # type: ignore[no-untyped-def]
    _, res = synthetic_run
    pre = res["models"]["fake-pretext"]["primary_tier_A"]
    for name in ("pretext_fiction_vs_none", "pretext_professional_vs_none"):
        assert pre[name]["mean_effect_treatment_minus_reference"] > 0.3
        assert pre[name]["p_holm"] < 0.05
    assert pre["cue_explicit_vs_none"]["mean_effect_treatment_minus_reference"] == 0
    for r in res["models"]["fake-null"]["primary_tier_A"].values():
        assert r["p_holm"] >= 0.05


def test_strict_replay_reproduces_results(synthetic_run) -> None:  # type: ignore[no-untyped-def]
    out, res = synthetic_run
    replayed = replay_synthetic(out / "recorded", out / "replayed")
    a = {k: v for k, v in res.items() if k != "pipeline_counts"}
    b = {k: v for k, v in replayed.items() if k != "pipeline_counts"}
    assert a == b
    assert (out / "recorded/report.md").read_text() == (out / "replayed/report.md").read_text()


def test_replay_subset_design_hits_cassette(synthetic_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    # Compact conditions are a subset of the full design with identical prompts.
    out, _ = synthetic_run
    res = replay_synthetic(out / "recorded", tmp_path / "x", design="compact")
    assert res["design"] == "compact"


def test_replay_with_changed_items_misses(synthetic_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    out, _ = synthetic_run
    src = tmp_path / "src"
    shutil.copytree(out / "recorded", src)
    items = src / "items.jsonl"
    items.write_text(items.read_text().replace("SYNTHETIC REQUEST 000", "SYNTHETIC REQUEST 999"))
    with pytest.raises(CassetteMissError):
        replay_synthetic(src, tmp_path / "y")


def test_compact_design_end_to_end(tmp_path: Path) -> None:
    res = run_synthetic(tmp_path, design="compact")
    assert res["design"] == "compact"
    assert all(
        r["matched_pairs_per_item"] == 1
        for r in res["models"]["fake-null"]["primary_tier_A"].values()
    )


class TestCli:
    def test_validate(self, repo_root: Path) -> None:
        assert (
            main(
                [
                    "validate",
                    "--config",
                    str(repo_root / "configs/synthetic.yaml"),
                    "--items",
                    str(repo_root / "data/synthetic/items.jsonl"),
                ]
            )
            == 0
        )

    def test_render(self, repo_root: Path, tmp_path: Path) -> None:
        out = tmp_path / "r.jsonl"
        assert (
            main(
                [
                    "render",
                    "--items",
                    str(repo_root / "data/synthetic/items.jsonl"),
                    "--design",
                    "compact",
                    "--out",
                    str(out),
                ]
            )
            == 0
        )
        assert len(out.read_text().splitlines()) == 16 * 5

    def test_render_stdout(self, repo_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main(["render", "--items", str(repo_root / "data/synthetic/items.jsonl")])
        assert len(capsys.readouterr().out.splitlines()) == 16 * 12

    def test_run_refuses_live_config(self, repo_root: Path, tmp_path: Path) -> None:
        cfg = repo_root / "configs/experiment_v1_draft.yaml"
        assert main(["run", "--config", str(cfg), "--out", str(tmp_path)]) == 2
        assert not any(tmp_path.iterdir())

    def test_run_analyze_report_offline(
        self, repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(repo_root)
        assert main(["run", "--config", "configs/synthetic.yaml", "--out", str(tmp_path)]) == 0
        res = json.loads((tmp_path / "results.json").read_text())
        assert set(res["models"]) == {"fake-null", "fake-pretext"}
        assert (
            main(
                [
                    "analyze",
                    "--responses",
                    str(tmp_path / "responses.jsonl"),
                    "--judgments",
                    str(tmp_path / "judgments.jsonl"),
                    "--items",
                    "data/synthetic/items.jsonl",
                    "--design",
                    "full",
                    "--out",
                    str(tmp_path / "a.json"),
                    "--report",
                    str(tmp_path / "a.md"),
                ]
            )
            == 0
        )
        assert (
            main(["report", "--results", str(tmp_path / "a.json"), "--out", str(tmp_path / "b.md")])
            == 0
        )
        assert (tmp_path / "a.md").read_text() == (tmp_path / "b.md").read_text()

    def test_synthetic(self, tmp_path: Path) -> None:
        assert main(["synthetic", "--out", str(tmp_path)]) == 0

    def test_historical_verify(self, repo_root: Path) -> None:
        assert main(["historical", "verify", "--repo", str(repo_root)]) == 0

    def test_scan(self, repo_root: Path) -> None:
        assert main(["scan", "--root", str(repo_root)]) == 0

    def test_design_compare_small(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["design", "compare", "--reps", "50"]) == 0
        assert "Compact power" in capsys.readouterr().out
