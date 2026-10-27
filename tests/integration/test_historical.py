"""Regression tests for the historical audit, run against committed redacted data."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from safetylens.historical import ARCHIVE_COMMIT, MODEL_FILES
from safetylens.historical.audit import load_redacted, run_audit
from safetylens.historical.flags import compute_flags
from safetylens.historical.manifest import load_manifest, verify_archive, verify_derived
from safetylens.historical.redact import FORBIDDEN_COLUMNS


@pytest.fixture(scope="module")
def audit_copy(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:  # type: ignore[type-arg]
    """Run the audit on a copy of historical/ so committed outputs can be compared."""
    repo = Path(__file__).resolve().parents[2]
    root = tmp_path_factory.mktemp("audit")
    shutil.copytree(repo / "historical" / "redacted", root / "historical" / "redacted")
    shutil.copytree(
        repo / "historical" / "original_outputs", root / "historical" / "original_outputs"
    )
    return root, run_audit(root)


def test_manifest_pins_archive_commit_and_derived_files(repo_root: Path) -> None:
    m = load_manifest(repo_root / "historical" / "MANIFEST.json")
    assert m["archive"]["commit"] == ARCHIVE_COMMIT
    assert len(m["archive"]["files"]) == 16
    assert verify_derived(repo_root, m) == []


def test_derived_file_tampering_detected(repo_root: Path, tmp_path: Path) -> None:
    m = load_manifest(repo_root / "historical" / "MANIFEST.json")
    shutil.copytree(repo_root / "historical", tmp_path / "historical")
    target = tmp_path / "historical" / "redacted" / "Llama-3.1-8B.csv"
    target.write_text(target.read_text().replace("True", "False", 1))
    assert verify_derived(tmp_path, m) == [
        "derived file changed: historical/redacted/Llama-3.1-8B.csv"
    ]


@pytest.mark.skipif(
    "SAFETYLENS_ARCHIVE" not in os.environ,
    reason="set SAFETYLENS_ARCHIVE to a local safetylens-research checkout",
)
def test_archive_matches_manifest(repo_root: Path) -> None:  # pragma: no cover - local only
    m = load_manifest(repo_root / "historical" / "MANIFEST.json")
    assert verify_archive(Path(os.environ["SAFETYLENS_ARCHIVE"]), m) == []


def test_redacted_files_contain_no_raw_text(repo_root: Path) -> None:
    for model in MODEL_FILES:
        cols = set(pd.read_csv(repo_root / "historical" / "redacted" / f"{model}.csv").columns)
        assert not cols & FORBIDDEN_COLUMNS
        assert {"response_sha256", "response_len", "prompt_sha256"} <= cols


def test_flag_counts(repo_root: Path) -> None:
    flags = compute_flags(load_redacted(repo_root))
    by = flags.groupby("model").sum(numeric_only=True)
    assert by.loc["Qwen3-32B", "model_api_error"] == 42
    assert by.loc["Qwen3-32B", "judged_error_text"] == 42
    assert by.loc["Qwen3-32B", "valid_observation"] == 0
    assert by.loc["Llama-3.1-8B", "judge_failed"] == 6
    assert by.loc["Llama-3.3-70B", "judge_failed"] == 3
    assert (by["model_api_error"].loc[["Llama-3.1-8B", "Llama-3.3-70B"]] == 0).all()
    assert (by["placeholder_prompt"] == 2).all()  # prompt 5, both conditions
    assert flags["finish_reason_unrecorded"].all()


def test_judge_failures_had_refusal_defaulted_to_false(repo_root: Path) -> None:
    red = load_redacted(repo_root)
    failed = red[red["safety_score"].isna()]
    assert len(failed) == 9 and not failed["refused"].astype(bool).any()


def test_historical_reproduction_matches_original_exactly(audit_copy) -> None:  # type: ignore[no-untyped-def]
    _, result = audit_copy
    assert result["comparison"] == {"stats": [], "refusal_rates": [], "divergence_summary": []}


def test_reproduction_demonstrates_original_defects(audit_copy) -> None:  # type: ignore[no-untyped-def]
    root, _ = audit_copy
    out = root / "historical" / "outputs" / "historical_reproduction"
    rates = pd.read_csv(out / "refusal_rates.csv")
    assert (rates["n"] == 18).all()  # failed judgments counted in denominators
    stats = pd.read_csv(out / "stats.csv").set_index("model")
    assert bool(stats.loc["Llama-3.3-70B", "significant"])  # uncorrected p < 0.05
    assert "Qwen3-32B" in stats.index  # invalid model included by the original method


def test_exploratory_excludes_qwen_and_uses_valid_denominators(audit_copy) -> None:  # type: ignore[no-untyped-def]
    _, result = audit_copy
    exp = result["exploratory"]
    assert "Qwen3-32B" not in exp["models"]
    assert "Qwen3-32B" in exp["excluded_models"]
    l8 = exp["models"]["Llama-3.1-8B"]
    deploy = l8["refusal_rates_valid_denominator"]["deploy"]
    assert (deploy["n_valid"], deploy["n_invalid_excluded"]) == (14, 4)
    assert l8["paired_refused"]["n_pairs"] == 14
    assert l8["paired_refused"]["excluded_units"] == {"judge_failed": 4}
    l70 = exp["models"]["Llama-3.3-70B"]
    assert l70["paired_safety_score"]["n_pairs"] == 16
    assert len(exp["multiple_comparisons"]["family"]) == 4
    for m in exp["models"].values():
        for k in ("paired_refused", "paired_safety_score"):
            assert m[k]["p_holm"] >= m[k]["p_value"]


def test_exploratory_is_labelled(audit_copy) -> None:  # type: ignore[no-untyped-def]
    root, result = audit_copy
    assert "NOT VALIDATED" in result["exploratory"]["label"]
    report = (root / "historical/outputs/exploratory_corrected/report.md").read_text()
    assert "NOT VALIDATED" in report and "Generated file" in report


def test_committed_outputs_match_regeneration(repo_root: Path, audit_copy) -> None:  # type: ignore[no-untyped-def]
    root, _ = audit_copy
    rels = [
        "historical/row_flags.csv",
        "historical/outputs/flag_summary.csv",
        "historical/outputs/historical_reproduction/stats.csv",
        "historical/outputs/historical_reproduction/refusal_rates.csv",
        "historical/outputs/historical_reproduction/divergence_summary.csv",
        "historical/outputs/historical_reproduction/comparison.json",
        "historical/outputs/exploratory_corrected/results.json",
        "historical/outputs/exploratory_corrected/report.md",
    ]
    stale = [r for r in rels if (root / r).read_bytes() != (repo_root / r).read_bytes()]
    assert stale == [], f"regenerate with `safetylens historical audit`: {stale}"


def test_results_json_has_no_nan_tokens(repo_root: Path) -> None:
    text = (repo_root / "historical/outputs/exploratory_corrected/results.json").read_text()
    assert "NaN" not in text
    json.loads(text)
