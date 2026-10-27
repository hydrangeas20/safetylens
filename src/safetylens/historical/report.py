"""Markdown rendering of the exploratory re-analysis (generated, never hand-edited)."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _f(x: Any, nd: int = 3) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def _ci(ci: dict[str, Any] | None) -> str:
    if not ci or ci.get("low") is None:
        return "n/a"
    return f"[{ci['low']:.3f}, {ci['high']:.3f}]"


def render_exploratory_report(res: dict[str, Any], flag_summary: pd.DataFrame) -> str:
    lines: list[str] = [
        "# Historical data: corrected exploratory re-analysis",
        "",
        "> **Generated file - do not edit.** Regenerate with `safetylens historical audit`.",
        ">",
        f"> **{res['label']}**",
        "",
        f"Source: {res['source']}. Comparison: {res['comparison']}.",
        "",
        "## Data validity",
        "",
        "| Model | Rows | API-error rows | Judge failures | Likely truncated (heuristic) "
        "| Placeholder prompt | Valid rows |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in flag_summary.itertuples():
        lines.append(
            f"| {r.model} | {r.rows} | {r.model_api_error} | {r.judge_failed} | "
            f"{r.likely_truncated_heuristic} | {r.placeholder_prompt} | {r.valid_observation} |"
        )
    lines += ["", "Finish reasons were not recorded for any archived row.", ""]
    if res["excluded_models"]:
        lines += ["## Excluded models", ""]
        for m, why in res["excluded_models"].items():
            lines.append(f"- **{m}**: {why}")
        lines.append("")

    fam = res["multiple_comparisons"]
    lines += [
        "## Paired eval-vs-deploy comparisons (harmful prompts)",
        "",
        f"Holm correction across a family of {len(fam['family'])} tests "
        f"({', '.join(fam['family'])}), alpha = {fam['alpha']}. Bootstrap: "
        f"{res['bootstrap']['n_boot']} resamples, seed {res['bootstrap']['seed']}.",
        "",
        "### Refusal (exact McNemar)",
        "",
        "| Model | Pairs | Excluded | Eval rate | Deploy rate | Difference | 95% CI "
        "| b / c | p | p (Holm) |",
        "|---|---:|---|---:|---:|---:|---|---|---:|---:|",
    ]
    for m, b in res["models"].items():
        p = b["paired_refused"]
        lines.append(
            f"| {m} | {p['n_pairs']} | {p['excluded_units'] or '-'} | {_f(p['rate_eval'])} | "
            f"{_f(p['rate_deploy'])} | {_f(p['risk_difference_eval_minus_deploy'])} | "
            f"{_ci(p['bootstrap_95ci'])} | {p['mcnemar_b_eval_only']} / "
            f"{p['mcnemar_c_deploy_only']} | {_f(p['p_value'], 4)} | {_f(p['p_holm'], 4)} |"
        )
    lines += [
        "",
        "### Safety score 1-10 (Wilcoxon signed-rank)",
        "",
        "| Model | Pairs | Excluded | Eval mean | Deploy mean | Mean diff | 95% CI | d_z "
        "| p | p (Holm) | paired-t p |",
        "|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    for m, b in res["models"].items():
        p = b["paired_safety_score"]
        lines.append(
            f"| {m} | {p['n_pairs']} | {p['excluded_units'] or '-'} | {_f(p['mean_eval'])} | "
            f"{_f(p['mean_deploy'])} | {_f(p['mean_difference_eval_minus_deploy'])} | "
            f"{_ci(p['bootstrap_95ci'])} | {_f(p['dz'])} | {_f(p['p_value'], 4)} | "
            f"{_f(p['p_holm'], 4)} | {_f(p['paired_t_p_value'], 4)} |"
        )
    lines += [
        "",
        "### Sensitivity: excluding pairs flagged by the truncation heuristic",
        "",
        "| Model | Outcome | Pairs | Difference | p (uncorrected) |",
        "|---|---|---:|---:|---:|",
    ]
    for m, b in res["models"].items():
        r = b["sensitivity_excluding_truncated_refused"]
        s = b["sensitivity_excluding_truncated_safety_score"]
        lines.append(
            f"| {m} | refusal | {r['n_pairs']} | "
            f"{_f(r['risk_difference_eval_minus_deploy'])} | {_f(r['p_value'], 4)} |"
        )
        lines.append(
            f"| {m} | safety score | {s['n_pairs']} | "
            f"{_f(s['mean_difference_eval_minus_deploy'])} | {_f(s['p_value'], 4)} |"
        )
    lines += [
        "",
        "## Category means (descriptive only; 1-5 pairs per cell, no tests)",
        "",
        "| Model | Category | Valid pairs | Mean diff (eval - deploy) |",
        "|---|---|---:|---:|",
    ]
    for m, b in res["models"].items():
        for cat, c in b["category_descriptive_only"].items():
            lines.append(
                f"| {m} | {cat} | {c['n_valid_pairs']} | "
                f"{_f(c['mean_difference_eval_minus_deploy'], 2)} |"
            )
    lines += [
        "",
        "## Safe controls (descriptive)",
        "",
        "| Model | Condition | Valid | Refused |",
        "|---|---|---:|---:|",
    ]
    for m, b in res["models"].items():
        for cond, c in b["safe_controls_descriptive"].items():
            lines.append(f"| {m} | {cond} | {c['n_valid']} | {c['n_refused']} |")
    lines += [
        "",
        "## How to read this",
        "",
        "- These numbers describe the archived run only. The deploy prompts add personas and "
        "justifications, so a difference cannot be attributed to evaluation framing.",
        "- Several deploy prompts are requests where helping is arguably correct; lower refusal "
        "there is not necessarily less safe.",
        "- The judge (claude-sonnet-4-6) saw the full framed prompt and was not validated "
        "against human labels.",
        "",
    ]
    return "\n".join(lines)
