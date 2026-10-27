from __future__ import annotations

import pytest

from safetylens.analysis.pairs import Observation, build_pairs


def obs(unit: int, cond: str, value: float | None, reason: str | None = None) -> Observation[float]:
    return Observation(unit, cond, value, reason)


def test_only_complete_valid_pairs_are_kept_and_exclusions_counted() -> None:
    data = [
        obs(1, "eval", 10.0),
        obs(1, "deploy", 6.0),
        obs(2, "eval", 9.0),
        obs(2, "deploy", None, "judge_failed"),
        obs(3, "eval", None, "model_api_error"),
        obs(3, "deploy", 5.0),
        obs(4, "eval", 8.0),  # deploy missing entirely
        obs(5, "deploy", 7.0),  # eval missing entirely
    ]
    s = build_pairs(data, "eval", "deploy")
    assert s.units == [1]
    assert (s.first, s.second) == ([10.0], [6.0])
    assert s.excluded == {
        "judge_failed": 1,
        "model_api_error": 1,
        "missing_deploy": 1,
        "missing_eval": 1,
    }
    assert s.n_pairs + s.n_excluded == 5


def test_invalid_without_reason_gets_generic_reason() -> None:
    s = build_pairs([obs(1, "a", None), obs(1, "b", 1.0)], "a", "b")
    assert s.excluded == {"invalid_a": 1}


def test_other_conditions_ignored() -> None:
    s = build_pairs([obs(1, "a", 1.0), obs(1, "b", 2.0), obs(1, "c", 3.0)], "a", "b")
    assert s.n_pairs == 1


def test_duplicates_raise() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        build_pairs([obs(1, "a", 1.0), obs(1, "a", 2.0)], "a", "b")


def test_failed_value_never_enters_sample() -> None:
    # A failed judgment must not appear as False/0 in the paired data.
    data = [
        Observation(i, c, None if i == 0 else True, "judge_failed" if i == 0 else None)
        for i in range(3)
        for c in ("eval", "deploy")
    ]
    s = build_pairs(data, "eval", "deploy")
    assert s.n_pairs == 2 and False not in s.first and False not in s.second
