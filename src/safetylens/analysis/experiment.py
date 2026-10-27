"""Analysis of a collected + judged experiment.

Contrast definitions follow the DRAFT protocol (docs/PROTOCOL.md). Which
contrasts are primary is an open decision recorded in docs/DECISIONS.md; the code
computes all of them and applies Holm across the family named in the call.

A contrast is a list of matched condition pairs (treatment, reference). For each
item, the contrast score is the mean of (y_treatment - y_reference) over its
matched pairs; an item contributes only if ALL its matched pairs are valid.
* one matched pair per item  -> exact McNemar on the paired binary outcomes
* several matched pairs      -> Wilcoxon signed-rank on item scores
Both report a seeded bootstrap CI of the mean item score (resampling items).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from safetylens.analysis.stats import bootstrap_mean_ci, holm_adjust, mcnemar_exact
from safetylens.items import (
    BASELINE,
    CUES,
    PRETEXTS,
    REGISTERS,
    Condition,
    Item,
)
from safetylens.judge import final_responses
from safetylens.records import JudgeStatus, JudgmentRecord, ResponseRecord

OUTCOMES = ("harmful_compliance", "refused")


@dataclass(frozen=True)
class Contrast:
    name: str
    pairs: tuple[tuple[Condition, Condition], ...]  # (treatment, reference)


def contrasts_for(design: str) -> list[Contrast]:
    def at_baseline(t: Condition) -> Contrast:
        return Contrast("", ((t, BASELINE),))

    if design == "compact":
        base = {
            "cue_explicit_vs_none": Condition("explicit", "terse", "none"),
            "register_conversational_vs_terse": Condition("none", "conversational", "none"),
            "pretext_fiction_vs_none": Condition("none", "terse", "fiction"),
            "pretext_professional_vs_none": Condition("none", "terse", "professional"),
        }
        return [Contrast(n, at_baseline(c).pairs) for n, c in base.items()]
    if design == "full":
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
        fic = tuple(
            (Condition(c, r, "fiction"), Condition(c, r, "none")) for c in CUES for r in REGISTERS
        )
        pro = tuple(
            (Condition(c, r, "professional"), Condition(c, r, "none"))
            for c in CUES
            for r in REGISTERS
        )
        return [
            Contrast("cue_explicit_vs_none", cue),
            Contrast("register_conversational_vs_terse", reg),
            Contrast("pretext_fiction_vs_none", fic),
            Contrast("pretext_professional_vs_none", pro),
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

    out: dict[str, Any] = {
        "contrast": contrast.name,
        "outcome": outcome,
        "matched_pairs_per_item": len(contrast.pairs),
        "n_items": len(scores),
        "excluded_items": dict(sorted(excluded.items())),
        "mean_effect_treatment_minus_reference": (
            sum(scores) / len(scores) if scores else math.nan
        ),
        "bootstrap_95ci": asdict(bootstrap_mean_ci(scores, seed=seed)),
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
        block: dict[str, Any] = {"primary_tier_A": {}, "secondary_refusal_tier_A": {}}
        for c in contrasts:
            block["primary_tier_A"][c.name] = analyse_contrast(
                cells, model, tier_a, c, "harmful_compliance", seed
            )
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


def render_report(res: dict[str, Any], title: str) -> str:
    def f(x: Any, nd: int = 3) -> str:
        return "n/a" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))

    lines = [
        f"# {title}",
        "",
        "> Generated from structured results. Do not edit by hand.",
        "",
        f"Design: **{res['design']}**. Primary outcome: {res['outcome_primary']}. "
        f"Holm family size: {len(res['multiple_comparisons']['family'])}.",
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
        "| Model | Contrast | Items | Excluded | Effect | 95% CI | Test | p | p (Holm) |",
        "|---|---|---:|---|---:|---|---|---:|---:|",
    ]
    for m, b in sorted(res["models"].items()):
        for c, r in sorted(b["primary_tier_A"].items()):
            ci = r["bootstrap_95ci"]
            ci_s = "n/a" if ci["low"] is None else f"[{ci['low']:.3f}, {ci['high']:.3f}]"
            lines.append(
                f"| {m} | {c} | {r['n_items']} | {r['excluded_items'] or '-'} | "
                f"{f(r['mean_effect_treatment_minus_reference'])} | {ci_s} | {r['test']} | "
                f"{f(r['p_value'], 4)} | {f(r['p_holm'], 4)} |"
            )
    lines += [
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
