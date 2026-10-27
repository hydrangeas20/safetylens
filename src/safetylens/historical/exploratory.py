"""Corrected EXPLORATORY re-analysis of the archived experiment.

Not a validated finding. The archived design confounds wording with persona /
pretext (see docs/DEFECTS.md W1) and its "expected refusal" labels are
contestable for several items (W2). These corrections fix the statistics; they
cannot fix the design.

Corrections relative to the original notebook:
* Observations are valid only if the model returned a real response AND the
  judge returned a parsed verdict. Invalid rows are excluded from every
  denominator and counted by reason.
* Models with no valid observations (Qwen3-32B: 42/42 API errors) produce no
  quantitative results.
* Eval-vs-deploy comparisons are paired by prompt and use only complete pairs:
  exact McNemar for refusal, Wilcoxon signed-rank (paired t secondary) for the
  1-10 safety score, paired effect size d_z, seeded bootstrap CIs.
* Holm correction across the full exploratory family (models x outcomes).
* Sensitivity analysis excluding pairs flagged by the truncation heuristic.
* Category results are descriptive only (n per category is 1-5 pairs).
"""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

import pandas as pd

from safetylens.analysis.pairs import Observation, PairedSample, build_pairs
from safetylens.analysis.stats import holm_adjust, paired_binary, paired_continuous, wilson_ci

FIRST, SECOND = "eval", "deploy"
LABEL = (
    "EXPLORATORY RE-ANALYSIS OF HISTORICAL DATA - NOT VALIDATED. Design confounds wording "
    "with persona/pretext; refusal labels contestable; single judge without human validation."
)


def _invalid_reason(row: pd.Series) -> str | None:
    if bool(row["model_api_error"]):
        return "model_api_error"
    if bool(row["judge_failed"]):
        return "judge_failed"
    return None


def _observations(
    frame: pd.DataFrame, outcome: str, *, drop_truncated: bool = False
) -> list[Observation[Any]]:
    obs: list[Observation[Any]] = []
    for _, row in frame.iterrows():
        reason = _invalid_reason(row)
        if reason is None and drop_truncated and bool(row["likely_truncated_heuristic"]):
            reason = "likely_truncated_heuristic"
        value: Any = None
        if reason is None:
            value = bool(row["refused"]) if outcome == "refused" else float(row["safety_score"])
        obs.append(Observation(row["prompt_id"], row["condition"], value, reason))
    return obs


def _clean(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    return value


def _paired_block(sample: PairedSample[Any], outcome: str, seed: int) -> dict[str, Any]:
    if outcome == "refused":
        res = paired_binary(sample.first, sample.second, seed=seed)
        return {
            "n_pairs": res.n_pairs,
            "excluded_units": dict(sorted(sample.excluded.items())),
            "rate_eval": res.rate_first,
            "rate_deploy": res.rate_second,
            "risk_difference_eval_minus_deploy": res.risk_difference,
            "bootstrap_95ci": asdict(res.bootstrap_ci),
            "mcnemar_b_eval_only": res.mcnemar.b,
            "mcnemar_c_deploy_only": res.mcnemar.c,
            "p_value": res.mcnemar.p_value,
            "test": "exact McNemar (two-sided)",
        }
    c = paired_continuous(sample.first, sample.second, seed=seed)
    return {
        "n_pairs": c.n_pairs,
        "excluded_units": dict(sorted(sample.excluded.items())),
        "mean_eval": c.mean_first,
        "mean_deploy": c.mean_second,
        "mean_difference_eval_minus_deploy": c.mean_difference,
        "dz": c.dz,
        "bootstrap_95ci": asdict(c.bootstrap_ci),
        "p_value": c.wilcoxon_p,
        "paired_t_p_value": c.paired_t_p,
        "test": "Wilcoxon signed-rank (two-sided; zero differences dropped)",
    }


def analyse(redacted: pd.DataFrame, flags: pd.DataFrame, *, seed: int = 20260614) -> dict[str, Any]:
    keys = ["model", "prompt_id", "condition"]
    data = redacted.merge(flags, on=keys, how="inner", validate="one_to_one")
    harmful = data[data["expected_refusal"].astype(bool)]
    controls = data[~data["expected_refusal"].astype(bool)]

    exclusions: dict[str, Any] = {}
    validity: dict[str, Any] = {}
    included_models: list[str] = []
    for model, sub in data.groupby("model"):
        reasons = pd.Series([_invalid_reason(row) for _, row in sub.iterrows()], dtype=object)
        validity[str(model)] = {
            "rows": len(sub),
            "valid_rows": int(reasons.isna().sum()),
            "invalid_by_reason": {str(k): int(v) for k, v in reasons.value_counts().items()},
        }
        if reasons.isna().any():
            included_models.append(str(model))
        else:
            exclusions[str(model)] = (
                "excluded from all quantitative results: no valid observations "
                f"({validity[str(model)]['invalid_by_reason']})"
            )

    per_model: dict[str, Any] = {}
    family: list[tuple[str, str]] = []
    for model in included_models:
        sub = harmful[harmful["model"] == model]
        block: dict[str, Any] = {"refusal_rates_valid_denominator": {}}
        for cond in (FIRST, SECOND):
            rows = sub[(sub["condition"] == cond) & sub["valid_observation"]]
            k, n = int(rows["refused"].astype(bool).sum()), len(rows)
            ci = wilson_ci(k, n)
            block["refusal_rates_valid_denominator"][cond] = {
                "n_valid": n,
                "n_refused": k,
                "rate": k / n if n else math.nan,
                "wilson_95ci": asdict(ci),
                "n_invalid_excluded": int((sub["condition"] == cond).sum()) - n,
            }
        for outcome in ("refused", "safety_score"):
            sample = build_pairs(_observations(sub, outcome), FIRST, SECOND)
            block[f"paired_{outcome}"] = _paired_block(sample, outcome, seed)
            family.append((model, outcome))
            sens = build_pairs(_observations(sub, outcome, drop_truncated=True), FIRST, SECOND)
            block[f"sensitivity_excluding_truncated_{outcome}"] = _paired_block(sens, outcome, seed)

        cats: dict[str, Any] = {}
        for cat, csub in sub.groupby("category"):
            s = build_pairs(_observations(csub, "safety_score"), FIRST, SECOND)
            diffs = [a - b for a, b in zip(s.first, s.second, strict=True)]
            cats[str(cat)] = {
                "n_valid_pairs": s.n_pairs,
                "excluded_units": dict(sorted(s.excluded.items())),
                "mean_difference_eval_minus_deploy": (
                    sum(diffs) / len(diffs) if diffs else math.nan
                ),
            }
        block["category_descriptive_only"] = cats

        csub = controls[(controls["model"] == model) & controls["valid_observation"]]
        block["safe_controls_descriptive"] = {
            cond: {
                "n_valid": int((csub["condition"] == cond).sum()),
                "n_refused": int(csub[csub["condition"] == cond]["refused"].astype(bool).sum()),
            }
            for cond in (FIRST, SECOND)
        }
        per_model[model] = block

    raw_p = [per_model[m][f"paired_{o}"]["p_value"] for m, o in family]
    adj = holm_adjust(raw_p)
    for (m, o), p_adj in zip(family, adj, strict=True):
        per_model[m][f"paired_{o}"]["p_holm"] = p_adj
        per_model[m][f"paired_{o}"]["holm_family_size"] = len(family)

    result = {
        "label": LABEL,
        "source": "historical/redacted (derived from safetylens-research @ b5d0dba)",
        "comparison": "eval minus deploy, paired by prompt_id, harmful prompts only",
        "bootstrap": {"n_boot": 10000, "seed": seed},
        "multiple_comparisons": {
            "method": "Holm",
            "family": [f"{m}:{o}" for m, o in family],
            "alpha": 0.05,
        },
        "validity": validity,
        "excluded_models": exclusions,
        "models": per_model,
    }
    cleaned: dict[str, Any] = _clean(result)
    return cleaned
