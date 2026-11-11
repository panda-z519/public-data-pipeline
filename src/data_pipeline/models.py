"""The one row shape every source is normalized into."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Record:
    source: str
    record_id: str
    title: str
    published_on: str  # ISO date, YYYY-MM-DD
    url: str
    record_type: str = ""
    organizations: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""

    def to_row(self) -> dict[str, str]:
        row = asdict(self)
        row["organizations"] = "; ".join(self.organizations)
        return row


ROW_FIELDS = list(Record.__dataclass_fields__)
