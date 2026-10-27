from __future__ import annotations

import math

import pytest
from scipy import stats as sps

from safetylens.analysis.stats import (
    bonferroni_adjust,
    bootstrap_mean_ci,
    holm_adjust,
    mcnemar_exact,
    paired_binary,
    paired_continuous,
    wilson_ci,
)


class TestWilson:
    def test_matches_archived_values(self) -> None:
        # refusal_rates.csv in the archive: Llama-3.1-8B eval, 15/18.
        ci = wilson_ci(15, 18)
        assert ci.low == pytest.approx(0.6077796189608428, abs=1e-12)
        assert ci.high == pytest.approx(0.9416342319413855, abs=1e-12)

    def test_zero_successes_has_zero_lower_bound(self) -> None:
        ci = wilson_ci(0, 18)
        assert ci.low == pytest.approx(0.0, abs=1e-12)
        assert ci.high == pytest.approx(0.17587922364665765, abs=1e-12)

    def test_empty_is_nan(self) -> None:
        ci = wilson_ci(0, 0)
        assert math.isnan(ci.low) and math.isnan(ci.high)

    @pytest.mark.parametrize(("k", "n"), [(-1, 5), (6, 5), (1, -1)])
    def test_invalid_counts_raise(self, k: int, n: int) -> None:
        with pytest.raises(ValueError, match="invalid counts"):
            wilson_ci(k, n)


class TestMcNemar:
    def test_counts_and_exact_p(self) -> None:
        first = [True] * 10 + [True] * 5 + [False] * 3
        second = [False] * 10 + [True] * 5 + [False] * 3
        res = mcnemar_exact(first, second)
        assert (res.b, res.c, res.n_pairs) == (10, 0, 18)
        assert res.p_value == pytest.approx(sps.binomtest(10, 10, 0.5).pvalue)
        assert res.p_value == pytest.approx(2 * 0.5**10)

    def test_no_discordant_pairs_gives_p_one(self) -> None:
        assert mcnemar_exact([True, False], [True, False]).p_value == 1.0

    def test_symmetry(self) -> None:
        a = [True, True, False, True, False]
        b = [False, True, True, False, False]
        assert mcnemar_exact(a, b).p_value == pytest.approx(mcnemar_exact(b, a).p_value)

    def test_unequal_lengths_raise(self) -> None:
        with pytest.raises(ValueError, match="equal length"):
            mcnemar_exact([True], [True, False])


class TestMultipleComparisons:
    def test_holm_textbook_example(self) -> None:
        p = [0.01, 0.04, 0.03, 0.005]
        # sorted: 0.005*4=0.02, 0.01*3=0.03, 0.03*2=0.06, 0.04*1=0.04 -> monotone 0.06
        assert holm_adjust(p) == pytest.approx([0.03, 0.06, 0.06, 0.02])

    def test_holm_caps_at_one_and_is_monotone(self) -> None:
        adj = holm_adjust([0.5, 0.6, 0.7])
        assert adj == pytest.approx([1.0, 1.0, 1.0])

    def test_holm_nan_not_counted_in_family(self) -> None:
        adj = holm_adjust([0.01, math.nan, 0.02])
        assert math.isnan(adj[1])
        assert adj[0] == pytest.approx(0.02) and adj[2] == pytest.approx(0.02)

    def test_holm_never_less_than_raw(self) -> None:
        p = [0.001, 0.2, 0.03, 0.04, 0.5]
        assert all(a >= r for a, r in zip(holm_adjust(p), p, strict=True))

    def test_holm_at_most_bonferroni(self) -> None:
        p = [0.001, 0.2, 0.03, 0.04, 0.5]
        assert all(
            h <= b + 1e-15 for h, b in zip(holm_adjust(p), bonferroni_adjust(p), strict=True)
        )

    def test_bonferroni(self) -> None:
        assert bonferroni_adjust([0.01, 0.4, math.nan])[:2] == pytest.approx([0.02, 0.8])


class TestPairedContinuous:
    def test_basic_quantities(self) -> None:
        a = [10.0, 9.0, 8.0, 10.0, 7.0]
        b = [6.0, 8.0, 8.0, 5.0, 7.0]
        res = paired_continuous(a, b, seed=1)
        d = [4.0, 1.0, 0.0, 5.0, 0.0]
        mean = sum(d) / 5
        sd = (sum((x - mean) ** 2 for x in d) / 4) ** 0.5
        assert res.n_pairs == 5
        assert res.mean_difference == pytest.approx(mean)
        assert res.dz == pytest.approx(mean / sd)
        assert res.wilcoxon_p == pytest.approx(sps.wilcoxon(a, b, zero_method="wilcox").pvalue)
        assert res.paired_t_p == pytest.approx(sps.ttest_rel(a, b).pvalue)

    def test_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="incomplete pairs"):
            paired_continuous([1.0, math.nan], [1.0, 2.0])

    def test_all_zero_differences(self) -> None:
        res = paired_continuous([3.0, 4.0], [3.0, 4.0])
        assert res.wilcoxon_p == 1.0
        assert math.isnan(res.dz)

    def test_too_few_pairs_is_nan(self) -> None:
        res = paired_continuous([1.0], [2.0])
        assert res.n_pairs == 1 and math.isnan(res.wilcoxon_p)

    def test_shape_mismatch(self) -> None:
        with pytest.raises(ValueError, match="equal length"):
            paired_continuous([1.0, 2.0], [1.0])


class TestBootstrapAndBinary:
    def test_bootstrap_deterministic(self) -> None:
        v = [0.0, 1.0, 1.0, 0.0, 1.0, -1.0]
        assert bootstrap_mean_ci(v, seed=3) == bootstrap_mean_ci(v, seed=3)

    def test_bootstrap_contains_mean(self) -> None:
        v = [0.2, 0.4, 0.1, 0.9, 0.5, 0.3]
        ci = bootstrap_mean_ci(v, seed=0)
        assert ci.low <= sum(v) / len(v) <= ci.high

    def test_bootstrap_empty(self) -> None:
        assert math.isnan(bootstrap_mean_ci([]).low)

    def test_paired_binary(self) -> None:
        res = paired_binary([True, True, False, True], [False, True, False, False], seed=0)
        assert res.rate_first == 0.75 and res.rate_second == 0.25
        assert res.risk_difference == 0.5
        assert (res.mcnemar.b, res.mcnemar.c) == (2, 0)

    def test_paired_binary_empty(self) -> None:
        res = paired_binary([], [])
        assert res.n_pairs == 0 and math.isnan(res.risk_difference)
