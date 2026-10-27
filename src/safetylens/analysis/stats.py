"""Statistical primitives for paired evaluation designs.

All functions take only valid observations. Building those (dropping incomplete
pairs, excluding failed judgments) is the caller's job and is done in
``safetylens.analysis.pairs`` so that exclusions are always counted and reported.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats as sps


@dataclass(frozen=True)
class Interval:
    low: float
    high: float


def wilson_ci(successes: int, n: int, conf: float = 0.95) -> Interval:
    """Wilson score interval. Returns NaN bounds for n == 0."""
    if n < 0 or successes < 0 or successes > n:
        raise ValueError(f"invalid counts: successes={successes}, n={n}")
    if n == 0:
        return Interval(math.nan, math.nan)
    z = float(sps.norm.ppf((1 + conf) / 2))
    p = successes / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return Interval((centre - spread) / denom, (centre + spread) / denom)


@dataclass(frozen=True)
class McNemarResult:
    n_pairs: int
    b: int  # first condition positive, second negative
    c: int  # first condition negative, second positive
    p_value: float
    method: str = "exact binomial (two-sided)"


def mcnemar_exact(first: Sequence[bool], second: Sequence[bool]) -> McNemarResult:
    """Exact McNemar test on paired binary outcomes.

    ``first[i]`` and ``second[i]`` must be the same unit (item) under two conditions.
    """
    if len(first) != len(second):
        raise ValueError("paired sequences must have equal length")
    b = sum(1 for x, y in zip(first, second, strict=True) if x and not y)
    c = sum(1 for x, y in zip(first, second, strict=True) if not x and y)
    p = 1.0 if b + c == 0 else float(sps.binomtest(b, b + c, 0.5, alternative="two-sided").pvalue)
    return McNemarResult(n_pairs=len(first), b=b, c=c, p_value=min(p, 1.0))


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p-values (family-wise error control).

    NaN p-values are not part of the family: they are returned as NaN and do not
    count towards m.
    """
    idx = [i for i, p in enumerate(p_values) if not math.isnan(p)]
    m = len(idx)
    adjusted = [math.nan] * len(p_values)
    order = sorted(idx, key=lambda i: p_values[i])
    running = 0.0
    for rank, i in enumerate(order):
        value = min(1.0, (m - rank) * p_values[i])
        running = max(running, value)
        adjusted[i] = running
    return adjusted


def bonferroni_adjust(p_values: Sequence[float]) -> list[float]:
    m = sum(1 for p in p_values if not math.isnan(p))
    return [math.nan if math.isnan(p) else min(1.0, p * m) for p in p_values]


@dataclass(frozen=True)
class PairedContinuousResult:
    n_pairs: int
    mean_first: float
    mean_second: float
    mean_difference: float  # first - second
    dz: float  # mean difference / SD of differences
    wilcoxon_p: float
    paired_t_p: float
    bootstrap_ci: Interval


def bootstrap_mean_ci(
    values: Sequence[float], *, n_boot: int = 10_000, conf: float = 0.95, seed: int = 0
) -> Interval:
    """Percentile bootstrap CI for a mean, resampling units. Deterministic given seed."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return Interval(math.nan, math.nan)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, arr.size, size=(n_boot, arr.size))
    means = arr[draws].mean(axis=1)
    alpha = (1 - conf) / 2
    return Interval(float(np.quantile(means, alpha)), float(np.quantile(means, 1 - alpha)))


def paired_continuous(
    first: Sequence[float], second: Sequence[float], *, seed: int = 0
) -> PairedContinuousResult:
    """Wilcoxon signed-rank (primary), paired t (secondary), d_z and bootstrap CI."""
    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    if a.shape != b.shape:
        raise ValueError("paired sequences must have equal length")
    if np.isnan(a).any() or np.isnan(b).any():
        raise ValueError("NaN in paired data: drop incomplete pairs before testing")
    n = int(a.size)
    d = a - b
    if n < 2:
        nan = math.nan
        return PairedContinuousResult(n, nan, nan, nan, nan, nan, nan, Interval(nan, nan))
    sd = float(d.std(ddof=1))
    dz = float(d.mean() / sd) if sd > 0 else math.nan
    if np.all(d == 0):
        wil_p = 1.0
        t_p = 1.0
    else:
        # zero_method="wilcox" drops zero differences, the conventional choice.
        wil_p = float(sps.wilcoxon(a, b, zero_method="wilcox").pvalue)
        t_p = float(sps.ttest_rel(a, b).pvalue) if sd > 0 else math.nan
    return PairedContinuousResult(
        n_pairs=n,
        mean_first=float(a.mean()),
        mean_second=float(b.mean()),
        mean_difference=float(d.mean()),
        dz=dz,
        wilcoxon_p=wil_p,
        paired_t_p=t_p,
        bootstrap_ci=bootstrap_mean_ci(d.tolist(), seed=seed),
    )


@dataclass(frozen=True)
class PairedBinaryResult:
    n_pairs: int
    rate_first: float
    rate_second: float
    risk_difference: float  # first - second
    bootstrap_ci: Interval
    mcnemar: McNemarResult


def paired_binary(
    first: Sequence[bool], second: Sequence[bool], *, seed: int = 0
) -> PairedBinaryResult:
    if len(first) != len(second):
        raise ValueError("paired sequences must have equal length")
    n = len(first)
    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    if n == 0:
        nan = math.nan
        return PairedBinaryResult(0, nan, nan, nan, Interval(nan, nan), mcnemar_exact([], []))
    return PairedBinaryResult(
        n_pairs=n,
        rate_first=float(a.mean()),
        rate_second=float(b.mean()),
        risk_difference=float((a - b).mean()),
        bootstrap_ci=bootstrap_mean_ci((a - b).tolist(), seed=seed),
        mcnemar=mcnemar_exact(list(first), list(second)),
    )
