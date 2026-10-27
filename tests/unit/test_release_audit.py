from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from safetylens.cli import main
from safetylens.release_audit import audit_history

FAKE_KEY = "gsk_" + "Q" * 30


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def commit(repo: Path, files: dict[str, str | None], message: str) -> None:
    for rel, text in files.items():
        path = repo / rel
        if text is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    commit(r, {"README.md": "clean\n"}, "init")
    return r


def kinds(report) -> set[str]:  # type: ignore[no-untyped-def]
    return {f.kind for f in report.blocking}


def test_clean_history_passes(repo: Path) -> None:
    report = audit_history(repo)
    assert report.blocking == []
    assert report.commits == 1


def test_secret_deleted_in_later_commit_is_still_found(repo: Path) -> None:
    commit(repo, {"config.env": f"KEY={FAKE_KEY}\n"}, "add config")
    commit(repo, {"config.env": None}, "remove config")
    assert not (repo / "config.env").exists()
    report = audit_history(repo)
    assert "secret:groq_key" in kinds(report)
    assert any(f.where.startswith("config.env@") for f in report.blocking)


def test_secret_on_unmerged_branch_is_found(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "side")
    commit(repo, {"x.txt": FAKE_KEY}, "side")
    git(repo, "checkout", "-q", "main")
    assert "secret:groq_key" in kinds(audit_history(repo))


def test_raw_response_column_in_history_is_found(repo: Path) -> None:
    commit(repo, {"data/out.csv": "model,response\nm,text\n"}, "data")
    commit(repo, {"data/out.csv": "model,response_sha256\nm,abc\n"}, "redact")
    assert "raw_text_column" in kinds(audit_history(repo))


def test_email_and_local_path_detection(repo: Path) -> None:
    commit(
        repo,
        {"notes.md": "contact someone@gmail.com\nok hamda@duck.com\nsee /home/alice/x\n"},
        "notes",
    )
    report = audit_history(repo)
    details = {(f.kind, f.detail) for f in report.blocking}
    assert ("email", "someone@gmail.com") in details
    assert ("local_path", "/home/alice/") in details
    assert not any(f.detail == "hamda@duck.com" for f in report.findings)


def test_commit_message_scanned_and_session_url_flagged_for_review(repo: Path) -> None:
    commit(
        repo,
        {"a.txt": "a"},
        f"msg {FAKE_KEY}\n\nClaude-Session: https://claude.ai/code/session_abc123",
    )
    report = audit_history(repo)
    assert any(f.kind == "secret:groq_key" and "message" in f.where for f in report.blocking)
    assert any(f.kind == "session_url" and f.severity == "review" for f in report.findings)


def test_archive_overlap(repo: Path, tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    git(archive, "init", "-q", "-b", "main")
    commit(archive, {"results/stats.csv": "model,p\nm,0.1\n", "raw.csv": "secret raw\n"}, "a")
    commit(repo, {"copied/stats.csv": "model,p\nm,0.1\n"}, "copy aggregate")
    ok = audit_history(repo, archive=archive, allowed_archive_paths=("results/stats.csv",))
    assert ok.blocking == []
    assert len(ok.archive_objects_shared) == 1
    commit(repo, {"leak.csv": "secret raw\n"}, "leak raw")
    bad = audit_history(repo, archive=archive, allowed_archive_paths=("results/stats.csv",))
    assert [f.detail for f in bad.blocking if f.kind == "archive_object"] == ["raw.csv"]


def test_scanner_allowlist_applies_by_path(repo: Path) -> None:
    commit(repo, {"tests/unit/test_scan.py": f'K = "{FAKE_KEY}"\n'}, "fixture")
    assert audit_history(repo).blocking == []


def test_cli_exit_codes(repo: Path, tmp_path: Path) -> None:
    assert main(["release-audit", "--repo", str(repo), "--json", str(tmp_path / "r.json")]) == 0
    assert '"blocking_count": 0' in (tmp_path / "r.json").read_text()
    commit(repo, {"k.txt": FAKE_KEY}, "leak")
    assert main(["release-audit", "--repo", str(repo)]) == 1
