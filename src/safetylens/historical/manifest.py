"""SHA-256 manifest pinning the archive and the derived files committed here."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from safetylens.historical import ARCHIVE_COMMIT, ARCHIVE_REPO

MANIFEST_VERSION = 1


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_tree(
    root: Path, *, exclude_dirs: tuple[str, ...] = (".git",)
) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in exclude_dirs:
            continue
        files[rel.as_posix()] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    return files


def build_manifest(
    archive_dir: Path, derived_root: Path, derived_paths: list[str]
) -> dict[str, Any]:
    """Archive file hashes plus hashes of derived files committed in this repo."""
    derived = {
        rel: {
            "sha256": sha256_file(derived_root / rel),
            "bytes": (derived_root / rel).stat().st_size,
        }
        for rel in sorted(derived_paths)
    }
    return {
        "manifest_version": MANIFEST_VERSION,
        "archive": {
            "repository": ARCHIVE_REPO,
            "commit": ARCHIVE_COMMIT,
            "visibility_note": "private; contains raw model outputs that must not be published",
            "files": hash_tree(archive_dir),
        },
        "derived": derived,
    }


def verify_archive(archive_dir: Path, manifest: dict[str, Any]) -> list[str]:
    """Return a list of problems; empty means the archive matches the manifest exactly."""
    expected: dict[str, dict[str, Any]] = manifest["archive"]["files"]
    actual = hash_tree(archive_dir)
    problems: list[str] = []
    for rel, meta in expected.items():
        if rel not in actual:
            problems.append(f"missing in archive: {rel}")
        elif actual[rel]["sha256"] != meta["sha256"]:
            problems.append(f"hash mismatch: {rel}")
    problems.extend(f"unexpected file in archive: {rel}" for rel in actual if rel not in expected)
    return problems


def verify_derived(repo_root: Path, manifest: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for rel, meta in manifest["derived"].items():
        path = repo_root / rel
        if not path.exists():
            problems.append(f"missing derived file: {rel}")
        elif sha256_file(path) != meta["sha256"]:
            problems.append(f"derived file changed: {rel}")
    return problems


def load_manifest(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
