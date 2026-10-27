"""Pre-commit / CI scan for secrets and unredacted model output.

Checks every tracked file:
1. Secret patterns (API keys, tokens, private keys).
2. Tabular files must not contain raw-text columns (prompt/response/...).
3. JSONL files must not contain non-synthetic response text.
4. Hazard terms that suggest operational harmful content; any hit needs human review.

This is a safety net, not a guarantee. docs/DATA_POLICY.md describes the manual
review that is still required before anything is made public.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "groq_key": re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    "openai_style_key": re.compile(r"\bsk-[A-Za-z0-9]{32,}"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}

# Terms whose presence suggests operational harmful detail. Kept deliberately short;
# hits require human review rather than proving harm.
HAZARD_TERMS: tuple[str, ...] = (
    "pseudoephedrine",
    "red phosphorus",
    "anhydrous ammonia",
    "ammonium nitrate",
    "blasting cap",
    "pipe threads",
    "end caps",
    "tablets of 500",
)

RAW_TEXT_COLUMNS = frozenset({"prompt", "response", "raw_response", "text", "completion"})
SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".lock")
# Files that legitimately contain the patterns above (definitions and their tests).
ALLOWLIST = frozenset({"src/safetylens/scan.py", "tests/unit/test_scan.py"})


@dataclass(frozen=True)
class Finding:
    path: str
    kind: str
    detail: str


def tracked_files(root: Path) -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True, text=True
        ).stdout
        return [root / p for p in out.split("\0") if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        skip = {".git", ".venv", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
        return [p for p in root.rglob("*") if p.is_file() and not skip & set(p.parts)]


def scan_text(rel: str, text: str) -> list[Finding]:
    findings = [
        Finding(rel, f"secret:{name}", "pattern match")
        for name, pat in SECRET_PATTERNS.items()
        if pat.search(text)
    ]
    lower = text.lower()
    findings.extend(Finding(rel, "hazard_term", t) for t in HAZARD_TERMS if t in lower)
    return findings


def scan_csv(rel: str, path: Path) -> list[Finding]:
    with path.open(encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh), [])
    bad = RAW_TEXT_COLUMNS.intersection(h.strip().lower() for h in header)
    return [Finding(rel, "raw_text_column", c) for c in sorted(bad)]


def scan_jsonl(rel: str, path: Path) -> list[Finding]:
    findings: list[Finding] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        result = row.get("result") if isinstance(row, dict) else None
        text = result.get("text") if isinstance(result, dict) else None
        if isinstance(text, str) and "[SYNTHETIC" not in text and "[MODEL ERROR" not in text:
            findings.append(Finding(rel, "unredacted_response", f"line {lineno}"))
    return findings


def scan_repo(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in tracked_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in ALLOWLIST or rel.endswith(SKIP_SUFFIXES) or not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(scan_text(rel, text))
        if rel.endswith(".csv"):
            findings.extend(scan_csv(rel, path))
        elif rel.endswith(".jsonl"):
            findings.extend(scan_jsonl(rel, path))
    return findings
