"""Convert archived per-model CSVs into a redacted form safe to commit.

Raw prompt and response text are replaced by SHA-256 hashes plus the derived
features the audit needs. Judge fields (labels, score, one-sentence reason) are
kept; the reasons were reviewed and contain meta-descriptions only.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd

from safetylens.quality import ends_with_terminal_punctuation, looks_like_error_text

REDACTED_COLUMNS: tuple[str, ...] = (
    "run_id",
    "model",
    "model_id",
    "prompt_id",
    "category",
    "expected_refusal",
    "condition",
    "prompt_sha256",
    "prompt_has_placeholder",
    "response_sha256",
    "response_len",
    "response_is_error_text",
    "response_ends_terminal_punct",
    "refused",
    "complied_with_harmful_request",
    "safety_score",
    "reason",
)

FORBIDDEN_COLUMNS: frozenset[str] = frozenset({"prompt", "response", "raw_response", "text"})


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _has_placeholder(text: str) -> bool:
    # Template slots such as "[ethnic group]" left unfilled in the prompt.
    return re.search(r"\[[a-z][a-z ]{2,40}\]", text) is not None


def redact_frame(raw: pd.DataFrame) -> pd.DataFrame:
    prompts = raw["prompt"].fillna("").astype(str)
    responses = raw["response"].fillna("").astype(str)
    out = pd.DataFrame(
        {
            "run_id": raw["run_id"].astype(str),
            "model": raw["model"],
            "model_id": raw["model_id"],
            "prompt_id": raw["prompt_id"],
            "category": raw["category"],
            "expected_refusal": raw["expected_refusal"],
            "condition": raw["condition"],
            "prompt_sha256": prompts.map(_sha),
            "prompt_has_placeholder": prompts.map(_has_placeholder),
            "response_sha256": responses.map(_sha),
            "response_len": responses.str.len(),
            "response_is_error_text": responses.map(looks_like_error_text),
            "response_ends_terminal_punct": responses.map(ends_with_terminal_punctuation),
            "refused": raw["refused"],
            "complied_with_harmful_request": raw["complied_with_harmful_request"],
            "safety_score": raw["safety_score"],
            "reason": raw["reason"],
        }
    )
    assert tuple(out.columns) == REDACTED_COLUMNS
    return out


def redact_file(raw_csv: Path, out_csv: Path) -> pd.DataFrame:
    frame = redact_frame(pd.read_csv(raw_csv))
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_csv, index=False, lineterminator="\n")
    return frame
