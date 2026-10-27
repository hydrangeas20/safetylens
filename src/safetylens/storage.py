"""Append-only JSONL storage. Records are never rewritten or deleted."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

R = TypeVar("R", bound=BaseModel)


class JsonlStore(Generic[R]):
    def __init__(self, path: Path, record_type: type[R]) -> None:
        self.path = path
        self.record_type = record_type

    def append(self, record: R) -> None:
        if not isinstance(record, self.record_type):
            raise TypeError(f"expected {self.record_type.__name__}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def __iter__(self) -> Iterator[R]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    yield self.record_type.model_validate_json(line)
                except ValueError as exc:
                    raise ValueError(f"{self.path}:{lineno}: corrupt record: {exc}") from exc

    def all(self) -> list[R]:
        return list(self)
