"""Build paired samples from long-format observations, counting every exclusion."""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

V = TypeVar("V")


@dataclass(frozen=True)
class Observation(Generic[V]):
    unit: Hashable  # e.g. item id
    condition: str
    value: V | None  # None => invalid / missing
    invalid_reason: str | None = None


@dataclass
class PairedSample(Generic[V]):
    first_condition: str
    second_condition: str
    units: list[Hashable] = field(default_factory=list)
    first: list[V] = field(default_factory=list)
    second: list[V] = field(default_factory=list)
    excluded: dict[str, int] = field(default_factory=dict)

    @property
    def n_pairs(self) -> int:
        return len(self.units)

    @property
    def n_excluded(self) -> int:
        return sum(self.excluded.values())


def build_pairs(
    observations: Iterable[Observation[V]], first_condition: str, second_condition: str
) -> PairedSample[V]:
    """Keep a unit only if both conditions have a valid value.

    Exclusion reasons are tallied per unit (one count per dropped unit), using the
    first non-empty reason found, so ``n_pairs + n_excluded`` equals the number of
    units seen in either condition.
    """
    by_unit: dict[Hashable, dict[str, Observation[V]]] = {}
    for obs in observations:
        if obs.condition not in (first_condition, second_condition):
            continue
        slot = by_unit.setdefault(obs.unit, {})
        if obs.condition in slot:
            raise ValueError(f"duplicate observation for unit={obs.unit!r} {obs.condition}")
        slot[obs.condition] = obs

    sample: PairedSample[V] = PairedSample(first_condition, second_condition)
    for unit in sorted(by_unit, key=repr):
        slot = by_unit[unit]
        a = slot.get(first_condition)
        b = slot.get(second_condition)
        reason: str | None = None
        if a is None:
            reason = f"missing_{first_condition}"
        elif b is None:
            reason = f"missing_{second_condition}"
        elif a.value is None:
            reason = a.invalid_reason or f"invalid_{first_condition}"
        elif b.value is None:
            reason = b.invalid_reason or f"invalid_{second_condition}"
        if reason is not None:
            sample.excluded[reason] = sample.excluded.get(reason, 0) + 1
            continue
        assert a is not None
        assert b is not None
        assert a.value is not None
        assert b.value is not None
        sample.units.append(unit)
        sample.first.append(a.value)
        sample.second.append(b.value)
    return sample
