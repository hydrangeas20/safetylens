from __future__ import annotations

import json
from pathlib import Path

from safetylens.scan import scan_csv, scan_jsonl, scan_repo, scan_text

FAKE_ANTHROPIC = "sk-ant-" + "a" * 30
FAKE_GROQ = "gsk_" + "B" * 30


def test_secrets_detected() -> None:
    kinds = {f.kind for f in scan_text("x", f"key={FAKE_ANTHROPIC}\nother={FAKE_GROQ}")}
    assert {"secret:anthropic_key", "secret:groq_key"} <= kinds


def test_private_key_detected() -> None:
    assert scan_text("x", "-----BEGIN RSA PRIVATE KEY-----")


def test_hazard_term_detected_case_insensitive() -> None:
    assert scan_text("x", "Uses Pseudoephedrine as ...")[0].kind == "hazard_term"


def test_clean_text() -> None:
    assert scan_text("x", "SafetyLens evaluates refusal behaviour.") == []


def test_raw_text_column_flagged(tmp_path: Path) -> None:
    p = tmp_path / "a.csv"
    p.write_text("model,Response,score\n")
    assert [f.detail for f in scan_csv("a.csv", p)] == ["response"]


def test_unredacted_jsonl_flagged(tmp_path: Path) -> None:
    p = tmp_path / "a.jsonl"
    rows = [{"result": {"text": "[SYNTHETIC-REFUSAL] no"}}, {"result": {"text": "real output"}}]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    findings = scan_jsonl("a.jsonl", p)
    assert len(findings) == 1 and findings[0].detail == "line 2"


def test_repository_is_clean(repo_root: Path) -> None:
    findings = scan_repo(repo_root)
    assert findings == [], "\n".join(f"{f.path}: {f.kind} {f.detail}" for f in findings)


def test_scan_without_git(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text(FAKE_GROQ)
    (tmp_path / "img.png").write_bytes(b"\x89PNG")
    assert [f.kind for f in scan_repo(tmp_path)] == ["secret:groq_key"]
