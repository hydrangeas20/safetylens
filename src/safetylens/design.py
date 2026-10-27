"""Transparent power and cost comparison of the compact (5) and full (12) designs.

Generative model (an ASSUMPTION, not an estimate from data):
  logit P(harmful compliance | item i, condition) =
      logit(p0) + u_i + b_cue*cue + b_reg*conversational + b_fic*fiction + b_pro*professional
  u_i ~ Normal(0, sigma_item^2)  (shared across an item's conditions -> within-item correlation)
No interactions are simulated. If interactions exist, the two designs estimate
different quantities: compact = effect at the baseline levels; full = effect
averaged over the other factors' levels.

Power is evaluated for the analysis actually implemented in
``safetylens.analysis.experiment`` (exact McNemar for compact, Wilcoxon on item
scores for full) at the worst-case Holm threshold alpha / m.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from functools import lru_cache

import numpy as np
from scipy import stats as sps

from safetylens.items import Condition, compact_design, full_design


@dataclass(frozen=True)
class Scenario:
    p0: float = 0.15
    sigma_item: float = 1.5
    b_cue: float = 0.0
    b_reg: float = 0.3
    b_fic: float = 0.8
    b_pro: float = 0.8
    target: str = "pretext_professional_vs_none"


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def _linpred(s: Scenario, c: Condition) -> float:
    return (
        _logit(s.p0)
        + s.b_cue * (c.cue == "explicit")
        + s.b_reg * (c.register == "conversational")
        + s.b_fic * (c.pretext == "fiction")
        + s.b_pro * (c.pretext == "professional")
    )


def _target_pairs(design: str, target: str) -> list[tuple[Condition, Condition]]:
    from safetylens.analysis.experiment import contrasts_for

    for c in contrasts_for(design):
        if c.name == target:
            return list(c.pairs)
    raise ValueError(target)


@lru_cache(maxsize=32)
def _mcnemar_reject_table(max_d: int, alpha: float) -> np.ndarray:
    """reject[d, b] for the exact two-sided McNemar test.

    With p = 0.5 the binomial is symmetric, so the two-sided exact p-value used by
    scipy's binomtest equals min(1, 2 * min(P(X <= b), P(X >= b))). Vectorised over b.
    Verified cell-by-cell against binomtest in tests/unit/test_design.py.
    """
    table = np.zeros((max_d + 1, max_d + 1), dtype=bool)
    for d in range(1, max_d + 1):
        b = np.arange(d + 1)
        lower = sps.binom.cdf(b, d, 0.5)
        upper = sps.binom.sf(b - 1, d, 0.5)
        p = np.minimum(1.0, 2 * np.minimum(lower, upper))
        table[d, : d + 1] = p <= alpha * (1 + 1e-12)
    table.setflags(write=False)
    return table


def simulate_power(
    design: str,
    n_items: int,
    scenario: Scenario,
    *,
    alpha: float,
    reps: int = 2000,
    seed: int = 0,
) -> float:
    rng = np.random.default_rng(seed)
    pairs = _target_pairs(design, scenario.target)
    conds = sorted({c for pair in pairs for c in pair})
    lp = np.array([_linpred(scenario, c) for c in conds])
    idx = {c: k for k, c in enumerate(conds)}
    u = rng.normal(0.0, scenario.sigma_item, size=(reps, n_items, 1))
    prob = 1 / (1 + np.exp(-(lp[None, None, :] + u)))
    y = rng.random(prob.shape) < prob  # (reps, items, conds)
    diffs = np.stack([y[:, :, idx[t]].astype(float) - y[:, :, idx[r]] for t, r in pairs], axis=2)
    if len(pairs) == 1:
        d = diffs[:, :, 0]
        b = (d > 0).sum(axis=1)
        c = (d < 0).sum(axis=1)
        table = _mcnemar_reject_table(n_items, alpha)
        rejects = table[b + c, b]
        return float(rejects.mean())
    scores = diffs.mean(axis=2)
    rejects = 0
    for r in range(reps):
        nz = scores[r][scores[r] != 0]
        if nz.size and sps.wilcoxon(nz).pvalue <= alpha:
            rejects += 1
    return rejects / reps


@dataclass(frozen=True)
class CostInputs:
    n_items_total: int
    n_models: int
    samples_per_cell: int = 1
    second_judge_fraction: float = 0.2
    mean_prompt_tokens: int = 120
    mean_response_tokens: int = 500
    judge_overhead_tokens: int = 450  # rubric + wrapper
    judge_output_tokens: int = 80


def cost_table(ci: CostInputs) -> dict[str, dict[str, float]]:
    """Call and token counts. Prices are NOT assumed; multiply by your provider's rates."""
    out: dict[str, dict[str, float]] = {}
    for name, conds in (("compact", compact_design()), ("full", full_design())):
        responses = ci.n_items_total * len(conds) * ci.n_models * ci.samples_per_cell
        judge_calls = responses * (1 + ci.second_judge_fraction)
        out[name] = {
            "conditions": len(conds),
            "model_calls": responses,
            "model_input_tokens": responses * ci.mean_prompt_tokens,
            "model_output_tokens": responses * ci.mean_response_tokens,
            "judge_calls": judge_calls,
            "judge_input_tokens": judge_calls
            * (ci.judge_overhead_tokens + ci.mean_prompt_tokens + ci.mean_response_tokens),
            "judge_output_tokens": judge_calls * ci.judge_output_tokens,
        }
    return out


def comparison_report(
    *, n_models: int = 3, n_contrasts: int = 4, reps: int = 2000, seed: int = 20261027
) -> str:
    m = n_models * n_contrasts
    alpha = 0.05 / m
    scenarios = {
        "S1 moderate pretext effect (b=0.8)": Scenario(),
        "S2 small pretext effect (b=0.5)": Scenario(b_fic=0.5, b_pro=0.5),
        "S3 large item heterogeneity (sigma=2.5)": Scenario(sigma_item=2.5),
        "S4 small cue effect, target cue (b=0.5)": Scenario(
            b_cue=0.5, target="cue_explicit_vs_none"
        ),
    }
    lines = [
        "# Design comparison: compact (5 conditions) vs full factorial (12 conditions)",
        "",
        "> Generated by `safetylens design compare`. Inputs are **assumptions**, not estimates.",
        "> Regenerate after changing assumptions; do not edit numbers by hand.",
        "",
        f"Primary family: {n_models} models x {n_contrasts} contrasts = {m} tests. Power is "
        f"computed at the worst-case Holm threshold alpha = 0.05/{m} = {alpha:.5f}. "
        f"Monte Carlo: {reps} replications, seed {seed}.",
        "",
        "Effects are subject-specific log-odds shifts in a random-intercept logistic model "
        "with baseline harmful-compliance probability p0 = 0.15 (see `safetylens.design`).",
        "",
        "## Power for the target contrast",
        "",
        "The equal-cost column gives the compact design 12/5 as many items, so both designs "
        "use the same number of model calls.",
        "",
        "| Scenario | Target | Items (tier A) | Compact power | Compact power, equal cost "
        "(items) | Full power |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for label, sc in scenarios.items():
        for n in (60, 120, 200):
            n_eq = round(n * 12 / 5)
            pc = simulate_power("compact", n, sc, alpha=alpha, reps=reps, seed=seed)
            pce = simulate_power("compact", n_eq, sc, alpha=alpha, reps=reps, seed=seed)
            pf = simulate_power("full", n, sc, alpha=alpha, reps=reps, seed=seed)
            lines.append(
                f"| {label} | {sc.target} | {n} | {pc:.2f} | {pce:.2f} ({n_eq}) | {pf:.2f} |"
            )
    lines += ["", "Scenario parameters:", ""]
    for label, sc in scenarios.items():
        lines.append(f"- {label}: `{asdict(sc)}`")
    ci = CostInputs(n_items_total=220, n_models=n_models)
    costs = cost_table(ci)
    lines += [
        "",
        "## Call and token volume (220 items: ~120 tier A, ~40 tier B, ~60 tier C)",
        "",
        f"Token assumptions: `{asdict(ci)}`. No prices are assumed; multiply by current "
        "provider rates before requesting budget approval.",
        "",
        "| Design | Conditions | Model calls | Model in/out tokens | Judge calls "
        "| Judge in/out tokens |",
        "|---|---:|---:|---|---:|---|",
    ]
    for name, c in costs.items():
        lines.append(
            f"| {name} | {c['conditions']:.0f} | {c['model_calls']:,.0f} | "
            f"{c['model_input_tokens']:,.0f} / {c['model_output_tokens']:,.0f} | "
            f"{c['judge_calls']:,.0f} | {c['judge_input_tokens']:,.0f} / "
            f"{c['judge_output_tokens']:,.0f} |"
        )
    lines += [
        "",
        "## Trade-offs (for decision DEC-1 in docs/DECISIONS.md)",
        "",
        "- **Compact** costs 5/12 of the full design. It estimates each effect only at the "
        "baseline levels (terse wording, no cue, no pretext) and cannot detect interactions, "
        "e.g. whether the cue matters only when a pretext is present.",
        "- **Full** reuses every response in several contrasts, which usually raises power per "
        "item, and it estimates effects averaged over the other factors plus interactions. "
        "Its estimand differs from the compact one if interactions exist.",
        "- Both designs hold the core request constant by construction (`safetylens.items`).",
        "- **Assumption that favours the full design:** responses to different conditions of "
        "the same item are simulated as independent given the item intercept. If items also "
        "differ in how strongly they respond to a factor (random slopes), the extra matched "
        "pairs carry less independent information and the full design's advantage shrinks. "
        "The pilot should estimate this before the design is frozen.",
        "- Null calibration (checked with 20,000 replications at alpha = 0.05/12): exact McNemar "
        "is conservative; the Wilcoxon test on item scores holds its nominal level.",
        "",
    ]
    return "\n".join(lines)
