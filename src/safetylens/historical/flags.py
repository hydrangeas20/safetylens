"""Programmatic data-quality flags for the archived observations.

Flags are computed from the redacted data only, so they are reproducible in CI.
They label rows; they never modify or drop the underlying records.
"""

from __future__ import annotations

import pandas as pd

# Truncation heuristic for archive rows (the archive did not record finish
# reasons and used max_tokens=300). In the archive, every response without
# terminal punctuation is >= 1170 characters and nearly all complete responses
# are far shorter, so the threshold sits below that cluster. It is a heuristic,
# used only for sensitivity analysis, never as ground truth.
TRUNCATION_MIN_CHARS = 1000

FLAG_COLUMNS: tuple[str, ...] = (
    "model_api_error",
    "judged_error_text",
    "judge_failed",
    "refusal_defaulted_on_judge_failure",
    "finish_reason_unrecorded",
    "likely_truncated_heuristic",
    "placeholder_prompt",
    "valid_observation",
)

KEY_COLUMNS: tuple[str, ...] = ("model", "prompt_id", "condition")


def compute_flags(redacted: pd.DataFrame) -> pd.DataFrame:
    api_error = redacted["response_is_error_text"].astype(bool)
    judge_failed = redacted["safety_score"].isna()
    flags = pd.DataFrame(
        {
            "model": redacted["model"],
            "prompt_id": redacted["prompt_id"],
            "condition": redacted["condition"],
            "model_api_error": api_error,
            # The judge produced labels for a response that was an error message.
            "judged_error_text": api_error & ~judge_failed,
            "judge_failed": judge_failed,
            # Original code set refused=False whenever the judge call failed, so the
            # stored `refused` value on these rows is a default, not an observation.
            "refusal_defaulted_on_judge_failure": judge_failed,
            "finish_reason_unrecorded": True,
            "likely_truncated_heuristic": (
                ~api_error
                & (redacted["response_len"] >= TRUNCATION_MIN_CHARS)
                & ~redacted["response_ends_terminal_punct"].astype(bool)
            ),
            "placeholder_prompt": redacted["prompt_has_placeholder"].astype(bool),
            "valid_observation": ~api_error & ~judge_failed,
        }
    )
    if flags.duplicated(list(KEY_COLUMNS)).any():
        raise ValueError("duplicate (model, prompt_id, condition) rows in archive data")
    return flags.sort_values(list(KEY_COLUMNS), kind="mergesort").reset_index(drop=True)


def summarise_flags(flags: pd.DataFrame) -> pd.DataFrame:
    """Count of each flag per model."""
    cols = [c for c in FLAG_COLUMNS if c != "finish_reason_unrecorded"]
    summary = flags.groupby("model")[cols].sum().astype(int)
    summary.insert(0, "rows", flags.groupby("model").size())
    return summary.reset_index()
