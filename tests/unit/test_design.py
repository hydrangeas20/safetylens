from __future__ import annotations

import pytest
from scipy import stats as sps

from safetylens.design import (
    CostInputs,
    Scenario,
    _mcnemar_reject_table,
    cost_table,
    simulate_power,
)

NULL = Scenario(b_cue=0, b_reg=0, b_fic=0, b_pro=0)


def test_reject_table_matches_binomtest() -> None:
    table = _mcnemar_reject_table(25, 0.05)
    for d in range(1, 26):
        for b in range(d + 1):
            assert table[d, b] == (sps.binomtest(b, d, 0.5).pvalue <= 0.05)


@pytest.mark.parametrize("design", ["compact", "full"])
def test_type_one_error_controlled_under_null(design: str) -> None:
    # 3000 reps: MC standard error at alpha=0.05 is ~0.004; allow 3 SE.
    power = simulate_power(design, 80, NULL, alpha=0.05, reps=3000, seed=11)
    assert power <= 0.05 + 0.012


@pytest.mark.parametrize("design", ["compact", "full"])
def test_power_increases_with_items(design: str) -> None:
    s = Scenario()
    small = simulate_power(design, 40, s, alpha=0.05, reps=600, seed=1)
    large = simulate_power(design, 160, s, alpha=0.05, reps=600, seed=1)
    assert large > small


def test_simulation_deterministic() -> None:
    a = simulate_power("full", 30, Scenario(), alpha=0.05, reps=200, seed=4)
    assert a == simulate_power("full", 30, Scenario(), alpha=0.05, reps=200, seed=4)


def test_cost_table_counts() -> None:
    t = cost_table(CostInputs(n_items_total=100, n_models=2, second_judge_fraction=0.5))
    assert t["compact"]["model_calls"] == 100 * 5 * 2
    assert t["full"]["model_calls"] == 100 * 12 * 2
    assert t["full"]["judge_calls"] == 100 * 12 * 2 * 1.5


def test_unknown_target_raises() -> None:
    with pytest.raises(ValueError, match="nope"):
        simulate_power("full", 10, Scenario(target="nope"), alpha=0.05, reps=10)
