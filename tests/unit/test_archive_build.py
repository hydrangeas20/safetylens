"""Archive build path (redaction + manifest) tested on a small fabricated archive.

The fabricated rows use benign placeholder text; they exist only to exercise the
code that turns a raw archive into committed derived files.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from safetylens.cli import main
from safetylens.historical import MODEL_FILES, ORIGINAL_OUTPUT_FILES
from safetylens.historical.audit import build_from_archive
from safetylens.historical.manifest import load_manifest, verify_archive, verify_derived
from safetylens.historical.redact import FORBIDDEN_COLUMNS, REDACTED_COLUMNS, redact_frame

RAW_SECRET_TEXT = "PLACEHOLDER RAW RESPONSE THAT MUST NOT BE COPIED"


def raw_rows(model: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "run_id": ["r1"] * 4,
            "model": [model] * 4,
            "model_id": ["mid"] * 4,
            "prompt_id": [0, 0, 1, 1],
            "category": ["c"] * 4,
            "expected_refusal": [True] * 4,
            "condition": ["eval", "deploy"] * 2,
            "prompt": ["Tell me about [ethnic group].", "q", "q2", "q3"],
            "response": [RAW_SECRET_TEXT, "[MODEL ERROR: Error code: 400 - x]", "ok.", "x" * 1200],
            "refused": [True, False, True, False],
            "complied_with_harmful_request": [False] * 4,
            "safety_score": [10.0, None, 9.0, 3.0],
            "reason": ["r"] * 4,
        }
    )


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    root = tmp_path / "archive"
    for model, rel in MODEL_FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        raw_rows(model).to_csv(root / rel, index=False)
    for rel in ORIGINAL_OUTPUT_FILES:
        (root / rel).write_text("model\nx\n")
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ignored")
    return root


def test_redact_frame_drops_raw_text_and_derives_features() -> None:
    out = redact_frame(raw_rows("m"))
    assert tuple(out.columns) == REDACTED_COLUMNS
    assert not FORBIDDEN_COLUMNS & set(out.columns)
    assert RAW_SECRET_TEXT not in out.to_csv()
    assert out["prompt_has_placeholder"].tolist() == [True, False, False, False]
    assert out["response_is_error_text"].tolist() == [False, True, False, False]
    assert out["response_len"].tolist()[3] == 1200
    assert len(out["response_sha256"][0]) == 64


def test_build_writes_manifest_and_verifies(archive: Path, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    derived = build_from_archive(archive, repo)
    assert len(derived) == 6
    manifest = load_manifest(repo / "historical" / "MANIFEST.json")
    assert set(manifest["archive"]["files"]) == set(MODEL_FILES.values()) | set(
        ORIGINAL_OUTPUT_FILES
    )  # .git excluded
    assert verify_archive(archive, manifest) == []
    assert verify_derived(repo, manifest) == []
    for model in MODEL_FILES:
        assert RAW_SECRET_TEXT not in (repo / "historical/redacted" / f"{model}.csv").read_text()


def test_archive_tampering_detected(archive: Path, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    build_from_archive(archive, repo)
    manifest = load_manifest(repo / "historical" / "MANIFEST.json")
    (archive / ORIGINAL_OUTPUT_FILES[0]).write_text("changed\n")
    (archive / "results" / "new.csv").write_text("x\n")
    (archive / MODEL_FILES["Qwen3-32B"]).unlink()
    problems = verify_archive(archive, manifest)
    assert f"hash mismatch: {ORIGINAL_OUTPUT_FILES[0]}" in problems
    assert "unexpected file in archive: results/new.csv" in problems
    assert f"missing in archive: {MODEL_FILES['Qwen3-32B']}" in problems
    (repo / "historical/redacted/Qwen3-32B.csv").unlink()
    assert verify_derived(repo, manifest) == [
        "missing derived file: historical/redacted/Qwen3-32B.csv"
    ]


def test_cli_build_and_verify(archive: Path, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    assert main(["historical", "build", "--archive", str(archive), "--repo", str(repo)]) == 0
    assert (
        main(["historical", "verify-archive", "--archive", str(archive), "--repo", str(repo)]) == 0
    )
    (archive / ORIGINAL_OUTPUT_FILES[1]).write_text("tampered\n")
    assert (
        main(["historical", "verify-archive", "--archive", str(archive), "--repo", str(repo)]) == 1
    )


def test_cli_audit_on_repo_copy(repo_root: Path, tmp_path: Path) -> None:
    import shutil

    shutil.copytree(repo_root / "historical", tmp_path / "historical")
    assert main(["historical", "audit", "--repo", str(tmp_path)]) == 0
