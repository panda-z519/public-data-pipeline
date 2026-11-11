"""Run a source, drop records already seen, and export new ones."""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from data_pipeline.models import ROW_FIELDS, Record
from data_pipeline.sources import Source

logger = logging.getLogger(__name__)


class SeenStore:
    """Remembers record ids between scheduled runs (a small JSON file)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._ids: set[str] = set()
        if path.exists():
            self._ids = set(json.loads(path.read_text(encoding="utf-8")))

    def is_new(self, key: str) -> bool:
        return key not in self._ids

    def add(self, key: str) -> None:
        self._ids.add(key)

    def flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(sorted(self._ids)), encoding="utf-8")
        tmp.replace(self._path)  # atomic, so a crash never corrupts the state


@dataclass
class RunResult:
    fetched: int
    new_records: list[Record]


def run(
    source: Source,
    *,
    keywords: list[str],
    since: str,
    max_records: int,
    seen: SeenStore,
) -> RunResult:
    fetched = 0
    new: list[Record] = []
    for record in source.fetch(keywords=keywords, since=since, max_records=max_records):
        fetched += 1
        key = f"{record.source}:{record.record_id}"
        if seen.is_new(key):
            seen.add(key)
            new.append(record)
    logger.info("run_done source=%s fetched=%s new=%s", source.name, fetched, len(new))
    return RunResult(fetched=fetched, new_records=new)


def append_csv(path: Path, records: Iterable[Record]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new_file = not path.exists()
    count = 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=ROW_FIELDS)
        if is_new_file:
            writer.writeheader()
        for record in records:
            writer.writerow(record.to_row())
            count += 1
    return count


def digest_markdown(records: list[Record], *, title: str) -> str:
    """A short weekly summary that can be emailed or posted to Slack as-is."""
    lines = [f"# {title}", "", f"{len(records)} new item(s).", ""]
    for record in records:
        orgs = f" ({', '.join(record.organizations)})" if record.organizations else ""
        lines.append(f"- {record.published_on} [{record.title}]({record.url}){orgs}")
    return "\n".join(lines) + "\n"
