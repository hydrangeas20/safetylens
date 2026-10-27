"""Transparent power and cost comparison of the compact and full factorial designs.

Generative model (an ASSUMPTION, not an estimate from data). For item i and condition c:

    logit P(harmful compliance) = logit(p0) + u_i + sum_f (b_f + s_if) * x_f(c)

    features x_f(c): cue        (explicit evaluation cue present)
                     register   (conversational wording)
                     prefix     (ANY preamble: filler, fiction or professional)
                     fiction    (fiction content, beyond the prefix)
                     professional (professional content, beyond the prefix)
    u_i  ~ Normal(0, sigma_item^2)    random intercept: correlates all of an item's conditions
    s_if ~ Normal(0, sigma_slope^2)   random slope: items differ in how much each factor
                                      matters (only for factors with b_f != 0, so
                                      true-null contrasts stay exactly null)

The pretext estimands compare a pretext with LENGTH-MATCHED FILLER, so their true
log-odds effect is the content coefficient alone; a model that only reacts to
"some preamble" (b_prefix > 0, content = 0) has a true pretext effect of exactly 0.

Power is evaluated for the analysis actually implemented in
``safetylens.analysis.experiment`` (exact McNemar for compact, Wilcoxon on item
scores for full) at the worst-case Holm threshold alpha / m. Because effects are
specified on the logit scale, the population-average effect on the probability
scale (the estimand the tests target) is computed and reported separately.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from functools import lru_cache

import numpy as np
from scipy import stats as sps

from safetylens.items import Condition, compact_design, full_design

FEATURES: tuple[str, ...] = ("cue", "register", "prefix", "fiction", "professional")


@dataclass(frozen=True)
class Scenario:
    p0: float = 0.15
    sigma_item: float = 1.5
    sigma_slope: float = 0.0
    b_cue: float = 0.0
    b_register: float = 0.3
    b_prefix: float = 0.0
    b_fiction: float = 0.8
    b_professional: float = 0.8
    target: str = "pretext_professional_vs_filler"

    def coefficients(self) -> np.ndarray:
        return np.array([getattr(self, f"b_{f}") for f in FEATURES])


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def features(c: Condition) -> np.ndarray:
    return np.array(
        [
            c.cue == "explicit",
            c.register == "conversational",
            c.pretext != "none",
            c.pretext == "fiction",
            c.pretext == "professional",
        ],
        dtype=float,
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


def _probabilities(
    scenario: Scenario, conds: list[Condition], shape: tuple[int, int], rng: np.random.Generator
) -> np.ndarray:
    """P(compliance) for every (rep, item, condition); shape (reps, items, conds)."""
    x = np.stack([features(c) for c in conds])  # (conds, F)
    b = scenario.coefficients()
    u = rng.normal(0.0, scenario.sigma_item, size=(*shape, 1))
    slope_sd = np.where(b != 0, scenario.sigma_slope, 0.0)
    slopes = rng.normal(0.0, 1.0, size=(*shape, len(FEATURES))) * slope_sd
    eta = _logit(scenario.p0) + u + (b + slopes) @ x.T
    return np.asarray(1 / (1 + np.exp(-eta)))


def true_effect(design: str, scenario: Scenario, *, n: int = 200_000, seed: int = 1) -> float:
    """Population-average effect on the probability scale (the tested estimand)."""
    rng = np.random.default_rng(seed)
    pairs = _target_pairs(design, scenario.target)
    conds = sorted({c for pair in pairs for c in pair})
    idx = {c: k for k, c in enumerate(conds)}
    prob = _probabilities(scenario, conds, (1, n), rng)[0]
    diffs = np.stack([prob[:, idx[t]] - prob[:, idx[r]] for t, r in pairs], axis=1)
    return float(diffs.mean())


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
    idx = {c: k for k, c in enumerate(conds)}
    prob = _probabilities(scenario, conds, (reps, n_items), rng)
    y = rng.random(prob.shape) < prob  # (reps, items, conds)
    diffs = np.stack([y[:, :, idx[t]].astype(float) - y[:, :, idx[r]] for t, r in pairs], axis=2)
    if len(pairs) == 1:
        d = diffs[:, :, 0]
        b = (d > 0).sum(axis=1)
        c = (d < 0).sum(axis=1)
        table = _mcnemar_reject_table(n_items, alpha)
        return float(table[b + c, b].mean())
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


SCENARIOS: dict[str, Scenario] = {
    "S1 moderate content effect, no slope variance": Scenario(),
    "S2 moderate content effect, slope sd 0.5": Scenario(sigma_slope=0.5),
    "S3 moderate content effect, slope sd 1.0": Scenario(sigma_slope=1.0),
    "S4 small content effect (0.5), slope sd 0.5": Scenario(
        b_fiction=0.5, b_professional=0.5, sigma_slope=0.5
    ),
    "S5 preamble-only model (prefix 0.8, content 0)": Scenario(
        b_prefix=0.8, b_fiction=0.0, b_professional=0.0, sigma_slope=1.0
    ),
    "S6 small cue effect (0.5), slope sd 0.5": Scenario(
        b_cue=0.5, sigma_slope=0.5, target="cue_explicit_vs_none"
    ),
}

NULL_CHECKS: dict[str, Scenario] = {
    "all effects zero": Scenario(
        b_register=0.0, b_fiction=0.0, b_professional=0.0, sigma_slope=1.0
    ),
    "preamble effect 0.8 with slope sd 1.0, content 0": SCENARIOS[
        "S5 preamble-only model (prefix 0.8, content 0)"
    ],
}


def comparison_report(
    *, n_models: int = 3, n_contrasts: int = 4, reps: int = 2000, seed: int = 20261027
) -> str:
    m = n_models * n_contrasts
    alpha = 0.05 / m
    n_compact, n_full = len(compact_design()), len(full_design())
    ratio = n_full / n_compact
    lines = [
        f"# Design comparison: compact ({n_compact} conditions) vs full factorial "
        f"({n_full} conditions)",
        "",
        "> Generated by `safetylens design compare`. Inputs are **assumptions**, not estimates.",
        "> Regenerate after changing assumptions; do not edit numbers by hand.",
        "",
        f"Primary family: {n_models} models × {n_contrasts} contrasts = {m} tests. Power is "
        f"computed at the worst-case Holm threshold α = 0.05/{m} = {alpha:.5f}. "
        f"Monte Carlo: {reps} replications, seed {seed}.",
        "",
        "## Generative model",
        "",
        "Random-intercept, random-slope logistic model (see `safetylens.design`). "
        "Baseline harmful-compliance probability p0 = 0.15, item intercept sd 1.5. "
        "Observations of the same item are correlated through the shared intercept and "
        "through item-specific slopes. Pretext effects are defined against length-matched "
        "filler, so a model that reacts only to *having* a preamble (S5) has a true pretext "
        "effect of zero.",
        "",
        "**True effect** is the population-average treatment-minus-reference difference in "
        "P(harmful compliance), which is the quantity the tests target. Logit-scale effects "
        "map to different probability-scale effects in the two designs because the full "
        "design averages over the other factors' levels.",
        "",
        "## Power for the target contrast",
        "",
        f"The equal-cost column gives the compact design {ratio:.2f}× as many items, so both "
        "designs use the same number of model calls.",
        "",
        "| Scenario | Target | True effect (compact / full) | Items (tier A) | Compact power "
        "| Compact power, equal cost (items) | Full power |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for label, sc in SCENARIOS.items():
        te_c = true_effect("compact", sc)
        te_f = true_effect("full", sc)
        for n in (60, 120, 200):
            n_eq = round(n * ratio)
            pc = simulate_power("compact", n, sc, alpha=alpha, reps=reps, seed=seed)
            pce = simulate_power("compact", n_eq, sc, alpha=alpha, reps=reps, seed=seed)
            pf = simulate_power("full", n, sc, alpha=alpha, reps=reps, seed=seed)
            lines.append(
                f"| {label} | {sc.target} | {te_c:+.3f} / {te_f:+.3f} | {n} | {pc:.2f} | "
                f"{pce:.2f} ({n_eq}) | {pf:.2f} |"
            )
    lines += ["", "Scenario parameters:", ""]
    for label, sc in SCENARIOS.items():
        lines.append(f"- {label}: `{asdict(sc)}`")

    null_reps = max(reps * 2, 1000)
    lines += [
        "",
        "## Type I error under correlated observations",
        "",
        f"Rejection rate for `pretext_professional_vs_filler` when its true effect is zero, at "
        f"nominal α = 0.05 ({null_reps} replications, 120 items). Monte Carlo standard error "
        f"≈ {math.sqrt(0.05 * 0.95 / null_reps):.3f}.",
        "",
        "| Null scenario | Compact (exact McNemar) | Full (Wilcoxon on item scores) |",
        "|---|---:|---:|",
    ]
    for label, sc in NULL_CHECKS.items():
        sc0 = Scenario(**{**asdict(sc), "target": "pretext_professional_vs_filler"})
        pc = simulate_power("compact", 120, sc0, alpha=0.05, reps=null_reps, seed=seed + 1)
        pf = simulate_power("full", 120, sc0, alpha=0.05, reps=null_reps, seed=seed + 1)
        lines.append(f"| {label} | {pc:.3f} | {pf:.3f} |")

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
        f"- **Compact** costs {n_compact}/{n_full} of the full design. It estimates each effect "
        "only at the baseline levels (terse wording, no cue) and cannot detect interactions, "
        "e.g. whether the cue matters only when a pretext is present.",
        "- **Full** reuses every response in several matched pairs, which raises power per "
        "item, and it estimates effects averaged over the other factors plus interactions. "
        "Its estimand differs from the compact one if interactions exist.",
        "- **Random slopes narrow the gap (compare S1, S2 and S3).** When items differ in how "
        "strongly a factor acts, extra matched pairs from the same item carry less independent "
        "information. In these scenarios the effect on power is modest, but the slope variance "
        "is unknown and the pilot should estimate it before the design is frozen.",
        "- Both designs hold the core request constant by construction (`safetylens.items`), "
        "and both include the length-matched filler control.",
        "",
    ]
    return "\n".join(lines)
