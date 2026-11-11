"""Data sources. Each one yields normalized Records and needs no paid proxy."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from data_pipeline.models import Record


class Source(Protocol):
    name: str

    def fetch(self, *, keywords: list[str], since: str, max_records: int) -> Iterator[Record]: ...
