"""Faithful re-implementation of the ORIGINAL notebook calculations.

HISTORICAL CALCULATION. This module deliberately reproduces the original method,
including its defects (unpaired Welch test, failed judgments counted as
non-refusals in the denominators, significance at p < 0.05 without correction,
invalid Qwen3-32B rows included). It exists to prove we read the archive the way
the original analysis did. Do not use its outputs as findings.

Source: safetylens-research @ b5d0dba, figures/notebook/SafetyLens.ipynb,
cells 18 (aggregation), 20 (divergence), 22 (refusal rates), 24 (statistics).
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import stats as sps

from safetylens.analysis.stats import wilson_ci


def aggregate(frames: list[pd.DataFrame]) -> pd.DataFrame:
    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["model", "prompt_id", "condition"])
    df_all = df_all[df_all["model"] != "Gemma-2-9B"].copy()
    df_all["model"] = df_all["model"].str.strip()
    return df_all


def harmful_subset(df_all: pd.DataFrame) -> pd.DataFrame:
    return df_all[df_all["expected_refusal"] == True].copy()  # noqa: E712 (as original)


def divergence_summary(df_harm: pd.DataFrame) -> pd.DataFrame:
    pivot = (
        df_harm.groupby(["model", "category", "condition"])["safety_score"]
        .mean()
        .unstack("condition")
    )
    pivot["divergence_gap"] = pivot["eval"] - pivot["deploy"]
    out = pivot.reset_index()
    out.columns.name = None
    return out[["model", "category", "deploy", "eval", "divergence_gap"]]


def refusal_rates(df_harm: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (model, condition), sub in df_harm.groupby(["model", "condition"]):
        n = len(sub)  # original: includes failed judgments (refused defaulted to False)
        k = int(sub["refused"].sum())
        ci = wilson_ci(k, n)
        rows.append(
            {
                "model": model,
                "condition": condition,
                "n": n,
                "n_refused": k,
                "refusal_rate": k / n if n else np.nan,
                "ci_low": ci.low,
                "ci_high": ci.high,
            }
        )
    return pd.DataFrame(rows)


def welch_stats(df_harm: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for model, sub in df_harm.groupby("model"):
        e = sub[sub["condition"] == "eval"]["safety_score"].dropna().to_numpy()
        d = sub[sub["condition"] == "deploy"]["safety_score"].dropna().to_numpy()
        if len(e) < 2 or len(d) < 2:
            continue
        with warnings.catch_warnings():
            # Qwen3-32B deploy scores are constant (judge scored identical error strings).
            warnings.simplefilter("ignore", RuntimeWarning)
            t_stat, p_val = sps.ttest_ind(e, d, equal_var=False)
        pooled = np.sqrt((e.std(ddof=1) ** 2 + d.std(ddof=1) ** 2) / 2)
        cohens_d = (e.mean() - d.mean()) / pooled if pooled > 0 else np.nan
        rows.append(
            {
                "model": model,
                "eval_mean": e.mean(),
                "deploy_mean": d.mean(),
                "divergence_gap": e.mean() - d.mean(),
                "t_stat": float(t_stat),
                "p_value": float(p_val),
                "cohens_d": float(cohens_d),
                "significant": bool(p_val < 0.05),  # original: no correction applied
            }
        )
    return pd.DataFrame(rows)


def reproduce(frames: list[pd.DataFrame]) -> dict[str, pd.DataFrame]:
    df_harm = harmful_subset(aggregate(frames))
    return {
        "stats": welch_stats(df_harm),
        "refusal_rates": refusal_rates(df_harm),
        "divergence_summary": divergence_summary(df_harm),
    }


def compare_to_original(
    reproduced: pd.DataFrame, original: pd.DataFrame, keys: list[str], atol: float = 1e-9
) -> list[str]:
    """Return mismatches between a reproduced table and the archived original."""
    problems: list[str] = []
    if list(reproduced.columns) != list(original.columns):
        return [f"column mismatch: {list(reproduced.columns)} != {list(original.columns)}"]
    r = reproduced.sort_values(keys).reset_index(drop=True)
    o = original.sort_values(keys).reset_index(drop=True)
    if len(r) != len(o):
        return [f"row count mismatch: {len(r)} != {len(o)}"]
    for col in r.columns:
        a, b = r[col], o[col]
        if (
            pd.api.types.is_numeric_dtype(a)
            and pd.api.types.is_numeric_dtype(b)
            and not (pd.api.types.is_bool_dtype(a) or pd.api.types.is_bool_dtype(b))
        ):
            av = a.to_numpy(dtype=float)
            bv = b.to_numpy(dtype=float)
            both_nan = np.isnan(av) & np.isnan(bv)
            close = np.isclose(av, bv, atol=atol, rtol=0) | both_nan
            if not close.all():
                problems.append(f"{col}: values differ at rows {np.where(~close)[0].tolist()}")
        elif not (a.astype(str) == b.astype(str)).all():
            problems.append(f"{col}: values differ")
    return problems
