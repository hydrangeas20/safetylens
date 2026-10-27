"""Orchestrates the historical audit: redact -> flag -> reproduce -> re-analyse.

Two entry points:
* ``build_from_archive`` (needs a local checkout of the private archive): writes the
  redacted CSVs, copies original aggregate outputs, writes the manifest.
* ``run_audit`` (offline, CI-safe): reads only committed derived files and writes
  the flags, the historical reproduction and the exploratory re-analysis.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from safetylens.historical import MODEL_FILES, ORIGINAL_OUTPUT_FILES
from safetylens.historical.exploratory import analyse
from safetylens.historical.flags import compute_flags, summarise_flags
from safetylens.historical.manifest import build_manifest, write_manifest
from safetylens.historical.redact import FORBIDDEN_COLUMNS, redact_file
from safetylens.historical.reproduce import compare_to_original, reproduce

HIST = Path("historical")
REDACTED = HIST / "redacted"
ORIGINALS = HIST / "original_outputs"
OUTPUTS = HIST / "outputs"
REPRO_KEYS = {
    "stats": ["model"],
    "refusal_rates": ["model", "condition"],
    "divergence_summary": ["model", "category"],
}


def redacted_path(model: str) -> Path:
    return REDACTED / f"{model}.csv"


def build_from_archive(archive_dir: Path, repo_root: Path) -> list[str]:
    derived: list[str] = []
    for model, rel in MODEL_FILES.items():
        out = repo_root / redacted_path(model)
        redact_file(archive_dir / rel, out)
        derived.append(redacted_path(model).as_posix())
    for rel in ORIGINAL_OUTPUT_FILES:
        dest = repo_root / ORIGINALS / Path(rel).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(archive_dir / rel, dest)
        derived.append((ORIGINALS / Path(rel).name).as_posix())
    manifest = build_manifest(archive_dir, repo_root, derived)
    write_manifest(repo_root / HIST / "MANIFEST.json", manifest)
    return derived


def load_redacted(repo_root: Path) -> pd.DataFrame:
    frames = []
    for model in MODEL_FILES:
        frame = pd.read_csv(repo_root / redacted_path(model))
        bad = FORBIDDEN_COLUMNS.intersection(frame.columns)
        if bad:
            raise ValueError(f"redacted file contains raw-text columns: {sorted(bad)}")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")


def run_audit(repo_root: Path) -> dict[str, Any]:
    redacted = load_redacted(repo_root)
    flags = compute_flags(redacted)
    _write_csv(flags, repo_root / HIST / "row_flags.csv")
    flag_summary = summarise_flags(flags)
    _write_csv(flag_summary, repo_root / OUTPUTS / "flag_summary.csv")

    # Historical reproduction: exactly the original inputs, in original file order.
    frames = [pd.read_csv(repo_root / redacted_path(m)) for m in MODEL_FILES]
    reproduced = reproduce(frames)
    repro_dir = repo_root / OUTPUTS / "historical_reproduction"
    comparison: dict[str, list[str]] = {}
    for name, table in reproduced.items():
        _write_csv(table, repro_dir / f"{name}.csv")
        original = pd.read_csv(repo_root / ORIGINALS / f"{name}.csv")
        comparison[name] = compare_to_original(table, original, REPRO_KEYS[name])
    (repro_dir / "comparison.json").write_text(
        json.dumps(
            {
                "label": "HISTORICAL CALCULATION - original method reproduced, defects included",
                "tolerance_abs": 1e-9,
                "mismatches": comparison,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    exploratory = analyse(redacted, flags)
    exp_dir = repo_root / OUTPUTS / "exploratory_corrected"
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "results.json").write_text(
        json.dumps(exploratory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    from safetylens.historical.report import render_exploratory_report

    (exp_dir / "report.md").write_text(
        render_exploratory_report(exploratory, flag_summary), encoding="utf-8"
    )
    return {"comparison": comparison, "exploratory": exploratory, "flags": flag_summary}
