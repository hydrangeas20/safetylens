from __future__ import annotations

import pytest
from scipy import stats as sps

from safetylens.design import (
    CostInputs,
    Scenario,
    _mcnemar_reject_table,
    cost_table,
    features,
    simulate_power,
    true_effect,
)
from safetylens.items import Condition

NULL = Scenario(b_cue=0, b_register=0, b_fiction=0, b_professional=0)
# Model reacts to having a preamble, not to its content: pretext-vs-filler is a true null.
PREAMBLE_ONLY = Scenario(b_prefix=0.8, b_fiction=0.0, b_professional=0.0, sigma_slope=1.0)


@pytest.mark.parametrize("alpha", [0.05, 0.05 / 12, 0.01])
def test_reject_table_matches_binomtest(alpha: float) -> None:
    table = _mcnemar_reject_table(60, alpha)
    for d in range(1, 61):
        for b in range(d + 1):
            assert table[d, b] == (sps.binomtest(b, d, 0.5).pvalue <= alpha), (d, b)


@pytest.mark.parametrize("design", ["compact", "full"])
@pytest.mark.parametrize("scenario", [NULL, PREAMBLE_ONLY], ids=["all-null", "preamble-only"])
def test_type_one_error_controlled_under_null(design: str, scenario: Scenario) -> None:
    # Correlated observations (random intercepts, and random slopes on the preamble
    # effect) must not inflate the false-positive rate of the content contrast.
    # 3000 reps: MC standard error at alpha=0.05 is ~0.004; allow 3 SE.
    power = simulate_power(design, 80, scenario, alpha=0.05, reps=3000, seed=11)
    assert power <= 0.05 + 0.012


@pytest.mark.parametrize("design", ["compact", "full"])
def test_preamble_only_model_has_zero_true_pretext_effect(design: str) -> None:
    assert true_effect(design, PREAMBLE_ONLY, n=20_000) == pytest.approx(0.0, abs=1e-12)
    # ...but the filler-vs-none control does detect the preamble effect.
    control = Scenario(**{**PREAMBLE_ONLY.__dict__, "target": "filler_vs_none"})
    assert true_effect(design, control, n=20_000) > 0.05


def test_true_effect_positive_for_content_effect() -> None:
    assert true_effect("full", Scenario(), n=20_000) > 0.05


def test_features_encode_prefix_for_all_preambles() -> None:
    assert features(Condition("none", "terse", "none"))[2] == 0
    for pre in ("filler", "fiction", "professional"):
        assert features(Condition("none", "terse", pre))[2] == 1
    assert features(Condition("none", "terse", "filler"))[3:].sum() == 0


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
    assert t["compact"]["model_calls"] == 100 * 6 * 2
    assert t["full"]["model_calls"] == 100 * 16 * 2
    assert t["full"]["judge_calls"] == 100 * 16 * 2 * 1.5


def test_unknown_target_raises() -> None:
    with pytest.raises(ValueError, match="nope"):
        simulate_power("full", 10, Scenario(target="nope"), alpha=0.05, reps=10)
