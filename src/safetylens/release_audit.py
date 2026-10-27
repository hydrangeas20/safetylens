"""Public-release audit of the full git history (not just the working tree).

Once a repository is public, every reachable object can be fetched, including
pull-request refs that GitHub keeps after a branch is deleted. Removing content
in a later commit does not unpublish it. This audit therefore scans:

* every blob reachable from any ref (branches, tags, ``refs/pull/*`` if fetched);
* every commit message;
* optionally, a local checkout of the private archive, to prove that none of its
  objects (history, raw data) exist here except an explicit allowlist.

It complements, and does not replace, human review (docs/PUBLIC_RELEASE_AUDIT.md).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from safetylens.scan import ALLOWLIST, SKIP_SUFFIXES, scan_content

# Emails that may legitimately appear: the owner's chosen commit address, bot and
# no-reply addresses, and documentation placeholders.
ALLOWED_EMAIL = re.compile(
    r"^(hamda@duck\.com|noreply@anthropic\.com|noreply@github\.com|"
    r"[0-9]+\+[A-Za-z0-9-]+@users\.noreply\.github\.com|[^@]+@example\.(com|org))$"
)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LOCAL_PATH = re.compile(
    r"(/home/[a-z][a-z0-9_-]*/|/Users/[A-Za-z][^/\s]*/|[A-Z]:\\Users\\|/mnt/user-data/|"
    r"/tmp/claude)"
)
SESSION_URL = re.compile(r"https://claude\.ai/code/session_[A-Za-z0-9]+")

# Findings a person has reviewed and judged not to be disclosures, pinned to the exact
# blob, kind and detail. Only that blob is exempt; any other version of the file, or any
# other finding in it, is still blocking. History is permanent, so a reviewed false
# positive cannot be removed, only documented.
REVIEWED_FALSE_POSITIVES: dict[tuple[str, str, str], str] = {
    ("e300168938a0fcc075b06ae033cd8386f4c1415e", "email", "someone@gmail.com"): (
        "fabricated test input in tests/unit/test_release_audit.py (first version)"
    ),
    ("e300168938a0fcc075b06ae033cd8386f4c1415e", "local_path", "/home/alice/"): (
        "fabricated test input in tests/unit/test_release_audit.py (first version)"
    ),
}


@dataclass(frozen=True)
class AuditFinding:
    severity: str  # "blocking" | "review"
    kind: str
    where: str
    detail: str


@dataclass
class AuditReport:
    refs: list[str] = field(default_factory=list)
    commits: int = 0
    roots: list[str] = field(default_factory=list)
    blobs_scanned: int = 0
    binary_blobs: int = 0
    archive_objects_checked: int = 0
    archive_objects_shared: list[str] = field(default_factory=list)
    findings: list[AuditFinding] = field(default_factory=list)

    @property
    def blocking(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == "blocking"]

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["blocking_count"] = len(self.blocking)
        return d


def _git(repo: Path, *args: str, input_: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=repo, input=input_, capture_output=True, check=True
    ).stdout


def _objects(repo: Path) -> list[tuple[str, str]]:
    """(sha, path) for every object reachable from any ref."""
    out = _git(repo, "rev-list", "--all", "--objects").decode()
    pairs = []
    for line in out.splitlines():
        sha, _, path = line.partition(" ")
        pairs.append((sha, path))
    return pairs


def _blob_contents(repo: Path, shas: list[str]) -> dict[str, bytes]:
    if not shas:
        return {}
    raw = _git(repo, "cat-file", "--batch", input_=("\n".join(shas) + "\n").encode())
    out: dict[str, bytes] = {}
    pos = 0
    while pos < len(raw):
        header_end = raw.index(b"\n", pos)
        sha, kind, size = raw[pos:header_end].decode().split()
        start = header_end + 1
        end = start + int(size)
        if kind == "blob":
            out[sha] = raw[start:end]
        pos = end + 1
    return out


def _text_findings(where: str, text: str, path: str | None = None) -> list[AuditFinding]:
    """Content checks; ``path`` selects file-type checks and the scanner allowlist."""
    if (path or where) in ALLOWLIST:
        return []
    findings = [
        AuditFinding("blocking", f.kind, where, f.detail) for f in scan_content(path or where, text)
    ]
    for email in sorted(set(EMAIL.findall(text))):
        if not ALLOWED_EMAIL.match(email):
            findings.append(AuditFinding("blocking", "email", where, email))
    for path in sorted(set(LOCAL_PATH.findall(text))):
        findings.append(AuditFinding("blocking", "local_path", where, path))
    return findings


def audit_history(
    repo: Path,
    *,
    archive: Path | None = None,
    allowed_archive_paths: tuple[str, ...] = (),
) -> AuditReport:
    report = AuditReport()
    report.refs = _git(repo, "for-each-ref", "--format=%(refname)").decode().split()
    report.commits = len(_git(repo, "rev-list", "--all").decode().split())
    report.roots = _git(repo, "rev-list", "--max-parents=0", "--all").decode().split()

    objects = _objects(repo)
    kinds = dict(
        line.split()
        for line in _git(
            repo,
            "cat-file",
            "--batch-check=%(objectname) %(objecttype)",
            input_=("\n".join(s for s, _ in objects) + "\n").encode(),
        )
        .decode()
        .splitlines()
    )
    blob_paths: dict[str, set[str]] = {}
    for sha, path in objects:
        if kinds.get(sha) == "blob":
            blob_paths.setdefault(sha, set()).add(path)
    contents = _blob_contents(repo, sorted(blob_paths))
    for sha, data in contents.items():
        for path in sorted(blob_paths[sha]):
            if path.endswith(SKIP_SUFFIXES):
                report.binary_blobs += 1
                break
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                report.binary_blobs += 1
                break
            report.blobs_scanned += 1
            for f in _text_findings(f"{path}@{sha[:7]}", text, path):
                reason = REVIEWED_FALSE_POSITIVES.get((sha, f.kind, f.detail))
                if reason is not None:
                    f = AuditFinding("review", f"reviewed:{f.kind}", f.where, reason)
                report.findings.append(f)

    log = _git(repo, "log", "--all", "--format=%H%x00%B%x01").decode()
    for entry in filter(None, (e.strip() for e in log.split("\x01"))):
        commit, _, message = entry.partition("\x00")
        where = f"commit {commit[:7]} message"
        report.findings.extend(_text_findings(where, message))
        for url in sorted(set(SESSION_URL.findall(message))):
            report.findings.append(AuditFinding("review", "session_url", where, url))

    if archive is not None:
        archive_pairs = _objects(archive)
        allowed = {sha for sha, path in archive_pairs if path in allowed_archive_paths}
        # Commits (history) and blobs (content) are what can leak. Trees only list names
        # and blob ids, and an identical directory produces an identical tree.
        archive_kinds = dict(
            line.split()
            for line in _git(
                archive,
                "cat-file",
                "--batch-check=%(objectname) %(objecttype)",
                input_=("\n".join(sorted({sha for sha, _ in archive_pairs})) + "\n").encode(),
            )
            .decode()
            .splitlines()
        )
        archive_objects = {
            sha for sha, kind in archive_kinds.items() if kind in ("commit", "blob", "tag")
        }
        report.archive_objects_checked = len(archive_objects)
        present = _git(
            repo,
            "cat-file",
            "--batch-check=%(objectname) %(objecttype)",
            input_=("\n".join(sorted(archive_objects)) + "\n").encode(),
        ).decode()
        shared = sorted(line.split()[0] for line in present.splitlines() if "missing" not in line)
        report.archive_objects_shared = shared
        for sha in shared:
            paths = sorted({p for s2, p in archive_pairs if s2 == sha and p}) or ["(no path)"]
            if sha not in allowed:
                report.findings.append(
                    AuditFinding("blocking", "archive_object", sha, ", ".join(paths))
                )
            else:
                report.findings.append(
                    AuditFinding("review", "archive_object_allowed", sha, ", ".join(paths))
                )
    return report


def render_summary(report: AuditReport) -> str:
    lines = [
        f"refs: {len(report.refs)} ({', '.join(report.refs)})",
        f"commits: {report.commits}; root commits: {', '.join(r[:7] for r in report.roots)}",
        f"text blobs scanned: {report.blobs_scanned}; binary blobs: {report.binary_blobs}",
    ]
    if report.archive_objects_checked:
        lines.append(
            f"archive objects checked: {report.archive_objects_checked}; "
            f"shared: {len(report.archive_objects_shared)}"
        )
    for f in report.findings:
        lines.append(f"[{f.severity}] {f.kind}: {f.where}: {f.detail}")
    lines.append(f"blocking findings: {len(report.blocking)}")
    return "\n".join(lines)
