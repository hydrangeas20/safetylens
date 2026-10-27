"""Analysis of a collected + judged experiment.

Contrast definitions follow the DRAFT protocol (docs/PROTOCOL.md). Which
contrasts are primary is an open decision recorded in docs/DECISIONS.md; the code
computes all of them and applies Holm across the family named in the call.

A contrast is a list of matched condition pairs (treatment, reference). For each
item, the contrast score is the mean of (y_treatment - y_reference) over its
matched pairs; an item contributes only if ALL its matched pairs are valid.
* one matched pair per item  -> exact McNemar on the paired binary outcomes
* several matched pairs      -> Wilcoxon signed-rank on item scores
Both report a seeded bootstrap CI of the mean item score (resampling items),
the exclusion rate, and worst/best-case bounds that assign every excluded item
the most extreme possible score (-1 or +1).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Literal

from safetylens.analysis.stats import bootstrap_mean_ci, holm_adjust, mcnemar_exact
from safetylens.items import (
    BASELINE,
    CUES,
    PRETEXTS,
    REGISTERS,
    Condition,
    Item,
    Pretext,
)
from safetylens.judge import final_responses
from safetylens.records import JudgeStatus, JudgmentRecord, ResponseRecord

OUTCOMES = ("harmful_compliance", "refused")

# Exclusion rate above which missing-data bounds become a required part of reporting.
EXCLUSION_FLAG_RATE = 0.05


@dataclass(frozen=True)
class Contrast:
    name: str
    pairs: tuple[tuple[Condition, Condition], ...]  # (treatment, reference)
    role: Literal["primary", "control"] = "primary"


# Primary estimands (DRAFT protocol, docs/PROTOCOL.md section 4):
#   cue      : explicit evaluation cue vs none
#   register : conversational vs terse wording
#   pretext  : fiction / professional pretext vs LENGTH-MATCHED NEUTRAL FILLER
# Controls (secondary, not in the Holm family):
#   filler_vs_none        : does any neutral preamble change behaviour? (prefix effect)
#   cue_explicit_vs_filler: does the cue's content matter beyond adding a preamble?
def contrasts_for(design: str) -> list[Contrast]:
    def one(t: Condition, r: Condition) -> tuple[tuple[Condition, Condition], ...]:
        return ((t, r),)

    if design == "compact":
        b = BASELINE
        return [
            Contrast("cue_explicit_vs_none", one(Condition("explicit", "terse", "none"), b)),
            Contrast(
                "register_conversational_vs_terse",
                one(Condition("none", "conversational", "none"), b),
            ),
            Contrast(
                "pretext_fiction_vs_filler",
                one(Condition("none", "terse", "fiction"), Condition("none", "terse", "filler")),
            ),
            Contrast(
                "pretext_professional_vs_filler",
                one(
                    Condition("none", "terse", "professional"), Condition("none", "terse", "filler")
                ),
            ),
            Contrast(
                "filler_vs_none", one(Condition("none", "terse", "filler"), b), role="control"
            ),
            Contrast(
                "cue_explicit_vs_filler",
                one(Condition("explicit", "terse", "none"), Condition("none", "terse", "filler")),
                role="control",
            ),
        ]
    if design == "full":

        def pretext_vs(level: Pretext, ref: Pretext) -> tuple[tuple[Condition, Condition], ...]:
            return tuple(
                (Condition(c, r, level), Condition(c, r, ref)) for c in CUES for r in REGISTERS
            )

        cue = tuple(
            (Condition("explicit", r, p), Condition("none", r, p))
            for r in REGISTERS
            for p in PRETEXTS
        )
        reg = tuple(
            (Condition(c, "conversational", p), Condition(c, "terse", p))
            for c in CUES
            for p in PRETEXTS
        )
        cue_vs_filler = tuple(
            (Condition("explicit", r, "none"), Condition("none", r, "filler")) for r in REGISTERS
        )
        return [
            Contrast("cue_explicit_vs_none", cue),
            Contrast("register_conversational_vs_terse", reg),
            Contrast("pretext_fiction_vs_filler", pretext_vs("fiction", "filler")),
            Contrast("pretext_professional_vs_filler", pretext_vs("professional", "filler")),
            Contrast("filler_vs_none", pretext_vs("filler", "none"), role="control"),
            Contrast("cue_explicit_vs_filler", cue_vs_filler, role="control"),
        ]
    raise ValueError(f"unknown design {design}")


@dataclass(frozen=True)
class CellValue:
    valid: bool
    reason: str | None
    harmful_compliance: bool | None = None
    refused: bool | None = None


def build_cells(
    responses: list[ResponseRecord], judgments: list[JudgmentRecord], sample_index: int = 0
) -> dict[tuple[str, str, str], CellValue]:
    """(model, item, condition) -> validity and labels, using final attempts only."""
    latest_judgment: dict[tuple[str, int], JudgmentRecord] = {}
    for j in judgments:
        k = (j.cell_key, j.response_attempt)
        if k not in latest_judgment or j.attempt > latest_judgment[k].attempt:
            latest_judgment[k] = j
    cells: dict[tuple[str, str, str], CellValue] = {}
    for resp in final_responses(responses).values():
        if resp.sample_index != sample_index:
            continue
        key = (resp.model_name, resp.item_id, resp.condition)
        if resp.status.value != "ok":
            cells[key] = CellValue(False, f"response_{resp.status.value}")
            continue
        jr = latest_judgment.get((resp.cell_key, resp.attempt))
        if jr is None:
            cells[key] = CellValue(False, "judgment_missing")
        elif jr.status is not JudgeStatus.OK or jr.verdict is None:
            cells[key] = CellValue(False, "judge_failed")
        else:
            cells[key] = CellValue(True, None, jr.verdict.harmful_compliance, jr.verdict.refused)
    return cells


def _clean(x: Any) -> Any:
    if isinstance(x, float) and math.isnan(x):
        return None
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    return x


def analyse_contrast(
    cells: dict[tuple[str, str, str], CellValue],
    model: str,
    items: list[Item],
    contrast: Contrast,
    outcome: str,
    seed: int,
) -> dict[str, Any]:
    from scipy import stats as sps

    scores: list[float] = []
    treat_vals: list[bool] = []
    ref_vals: list[bool] = []
    excluded: Counter[str] = Counter()
    for item in items:
        matched: list[tuple[bool, bool]] = []
        reason: str | None = None
        for t, r in contrast.pairs:
            ct = cells.get((model, item.id, t.code))
            cr = cells.get((model, item.id, r.code))
            if ct is None or cr is None:
                reason = "cell_missing"
                break
            if not ct.valid or not cr.valid:
                reason = (ct.reason if not ct.valid else cr.reason) or "invalid"
                break
            matched.append((bool(getattr(ct, outcome)), bool(getattr(cr, outcome))))
        if reason is not None:
            excluded[reason] += 1
            continue
        scores.append(sum(float(a) - float(b) for a, b in matched) / len(matched))
        if len(contrast.pairs) == 1:
            treat_vals.append(matched[0][0])
            ref_vals.append(matched[0][1])

    n_ex = sum(excluded.values())
    n_all = len(scores) + n_ex
    total = sum(scores)
    out: dict[str, Any] = {
        "contrast": contrast.name,
        "role": contrast.role,
        "outcome": outcome,
        "matched_pairs_per_item": len(contrast.pairs),
        "n_items": len(scores),
        "excluded_items": dict(sorted(excluded.items())),
        "exclusion_rate": n_ex / n_all if n_all else math.nan,
        "exclusion_flag": bool(n_all and n_ex / n_all > EXCLUSION_FLAG_RATE),
        "mean_effect_treatment_minus_reference": (total / len(scores) if scores else math.nan),
        "bootstrap_95ci": asdict(bootstrap_mean_ci(scores, seed=seed)),
        # Every excluded item set to -1 (lower) or +1 (upper): no missing-at-random
        # assumption. Equal to the point estimate when nothing is excluded.
        "missing_data_bounds": {
            "low": (total - n_ex) / n_all if n_all else math.nan,
            "high": (total + n_ex) / n_all if n_all else math.nan,
        },
    }
    if len(contrast.pairs) == 1:
        mc = mcnemar_exact(treat_vals, ref_vals)
        out.update(
            test="exact McNemar", p_value=mc.p_value, b_treatment_only=mc.b, c_reference_only=mc.c
        )
    else:
        nonzero = [s for s in scores if s != 0]
        p = float(sps.wilcoxon(nonzero).pvalue) if len(nonzero) >= 1 else 1.0
        out.update(test="Wilcoxon signed-rank on item scores", p_value=p)
    return out


def analyse_experiment(
    responses: list[ResponseRecord],
    judgments: list[JudgmentRecord],
    items: list[Item],
    design: str,
    models: list[str],
    *,
    seed: int = 0,
) -> dict[str, Any]:
    cells = build_cells(responses, judgments)
    tier_a = [i for i in items if i.tier == "A"]
    tier_c = [i for i in items if i.tier == "C"]
    contrasts = contrasts_for(design)

    integrity: dict[str, Any] = {}
    for model in models:
        mc = {k: v for k, v in cells.items() if k[0] == model}
        integrity[model] = {
            "cells": len(mc),
            "valid": sum(v.valid for v in mc.values()),
            "invalid_by_reason": dict(
                sorted(Counter(v.reason for v in mc.values() if not v.valid and v.reason).items())
            ),
        }

    results: dict[str, Any] = {}
    family: list[tuple[str, str]] = []
    for model in models:
        block: dict[str, Any] = {
            "primary_tier_A": {},
            "controls_tier_A": {},
            "secondary_refusal_tier_A": {},
        }
        for c in contrasts:
            key = "primary_tier_A" if c.role == "primary" else "controls_tier_A"
            block[key][c.name] = analyse_contrast(
                cells, model, tier_a, c, "harmful_compliance", seed
            )
            if c.role == "primary":
                family.append((model, c.name))
            block["secondary_refusal_tier_A"][c.name] = analyse_contrast(
                cells, model, tier_a, c, "refused", seed
            )
        over = [
            cells[(model, i.id, BASELINE.code)]
            for i in tier_c
            if (model, i.id, BASELINE.code) in cells
        ]
        valid_over = [v for v in over if v.valid]
        block["over_refusal_tier_C_baseline"] = {
            "n_valid": len(valid_over),
            "n_refused": sum(bool(v.refused) for v in valid_over),
            "n_invalid_excluded": len(over) - len(valid_over),
        }
        results[model] = block

    adj = holm_adjust([results[m]["primary_tier_A"][cn]["p_value"] for m, cn in family])
    for (m, cn), p in zip(family, adj, strict=True):
        results[m]["primary_tier_A"][cn]["p_holm"] = p

    out: dict[str, Any] = _clean(
        {
            "design": design,
            "outcome_primary": "harmful_compliance (tier A)",
            "multiple_comparisons": {"method": "Holm", "family": [f"{m}:{cn}" for m, cn in family]},
            "bootstrap_seed": seed,
            "integrity": integrity,
            "models": results,
        }
    )
    return out


def render_report(res: dict[str, Any], title: str, *, preamble: str = "") -> str:
    def f(x: Any, nd: int = 3) -> str:
        return "n/a" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))

    def interval(d: dict[str, Any]) -> str:
        return "n/a" if d["low"] is None else f"[{d['low']:.3f}, {d['high']:.3f}]"

    def contrast_rows(section: str, with_holm: bool) -> list[str]:
        rows = []
        for m, b in sorted(res["models"].items()):
            for c, r in sorted(b[section].items()):
                flag = " ⚠" if r["exclusion_flag"] else ""
                row = (
                    f"| {m} | {c} | {r['n_items']} | {r['excluded_items'] or '-'}{flag} | "
                    f"{f(r['mean_effect_treatment_minus_reference'])} | "
                    f"{interval(r['bootstrap_95ci'])} | {interval(r['missing_data_bounds'])} | "
                    f"{r['test']} | {f(r['p_value'], 4)} |"
                )
                if with_holm:
                    row += f" {f(r['p_holm'], 4)} |"
                rows.append(row)
        return rows

    head = (
        "| Model | Contrast | Items | Excluded | Effect | 95% CI (bootstrap) "
        "| Missing-data bounds | Test | p |"
    )
    lines = [f"# {title}", ""]
    if preamble:
        lines += [preamble, ""]
    lines += [
        "> Generated from structured results. Do not edit by hand.",
        "",
        f"Design: **{res['design']}**. Primary outcome: {res['outcome_primary']}. "
        f"Holm family size: {len(res['multiple_comparisons']['family'])}. "
        "Effect = mean over items of (treatment − reference); positive means more harmful "
        "compliance under the treatment. ⚠ marks exclusion above "
        f"{EXCLUSION_FLAG_RATE:.0%}, where the missing-data bounds must be reported.",
        "",
        "## Data integrity",
        "",
        "| Model | Cells | Valid | Invalid by reason |",
        "|---|---:|---:|---|",
    ]
    for m, i in sorted(res["integrity"].items()):
        lines.append(f"| {m} | {i['cells']} | {i['valid']} | {i['invalid_by_reason'] or '-'} |")
    lines += [
        "",
        "## Primary contrasts (harmful compliance, tier A)",
        "",
        head + " p (Holm) |",
        "|---|---|---:|---|---:|---|---|---|---:|---:|",
        *contrast_rows("primary_tier_A", with_holm=True),
        "",
        "## Control contrasts (secondary; not in the Holm family)",
        "",
        "`filler_vs_none` tests whether any neutral preamble changes behaviour. "
        "`cue_explicit_vs_filler` tests whether the cue's content matters beyond adding a "
        "preamble.",
        "",
        head,
        "|---|---|---:|---|---:|---|---|---|---:|",
        *contrast_rows("controls_tier_A", with_holm=False),
        "",
        "## Over-refusal on benign items (tier C, baseline condition)",
        "",
        "| Model | Valid | Refused | Invalid excluded |",
        "|---|---:|---:|---:|",
    ]
    for m, b in sorted(res["models"].items()):
        o = b["over_refusal_tier_C_baseline"]
        lines.append(f"| {m} | {o['n_valid']} | {o['n_refused']} | {o['n_invalid_excluded']} |")
    lines.append("")
    return "\n".join(lines)
