"""Record / replay of provider results keyed by a hash of the full request.

Replay is strict: a request that is not in the cassette raises, so a replayed
run can never silently fall through to a live call or invent a response.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from safetylens.providers.base import Provider
from safetylens.records import ProviderRequest, ProviderResult


class CassetteMissError(KeyError):
    pass


def request_key(request: ProviderRequest, occurrence: int = 0) -> str:
    payload = json.dumps(request.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(f"{payload}|{occurrence}".encode()).hexdigest()


@dataclass
class RecordingProvider:
    """Wraps a provider and appends every (request, result) to a cassette file."""

    inner: Provider
    cassette: Path
    name: str = "recording"
    _seen: dict[str, int] = field(default_factory=dict)

    @property
    def is_live(self) -> bool:
        return self.inner.is_live

    def generate(self, request: ProviderRequest) -> ProviderResult:
        base = request_key(request)
        occ = self._seen.get(base, 0)
        self._seen[base] = occ + 1
        result = self.inner.generate(request)
        self.cassette.parent.mkdir(parents=True, exist_ok=True)
        with self.cassette.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {"key": request_key(request, occ), "result": result.model_dump(mode="json")},
                    sort_keys=True,
                )
            )
            fh.write("\n")
        return result


@dataclass
class ReplayProvider:
    cassette: Path
    name: str = "replay"
    is_live: bool = False
    _table: dict[str, ProviderResult] = field(default_factory=dict)
    _seen: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for line in self.cassette.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                self._table[row["key"]] = ProviderResult.model_validate(row["result"])

    def generate(self, request: ProviderRequest) -> ProviderResult:
        base = request_key(request)
        occ = self._seen.get(base, 0)
        self._seen[base] = occ + 1
        key = request_key(request, occ)
        if key not in self._table:
            raise CassetteMissError(f"request not in cassette {self.cassette} (occurrence {occ})")
        return self._table[key]
