"""Command line entry point, suitable for cron or any scheduler."""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta
from pathlib import Path

from data_pipeline.pipeline import SeenStore, append_csv, digest_markdown, run
from data_pipeline.sources.federal_register import FederalRegisterSource


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect new public records into a CSV.")
    parser.add_argument("--keyword", action="append", default=[], help="repeatable")
    parser.add_argument("--days", type=int, default=7, help="look back this many days")
    parser.add_argument("--max-records", type=int, default=500)
    parser.add_argument("--out", type=Path, default=Path("output"))
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    since = (date.today() - timedelta(days=args.days)).isoformat()
    seen = SeenStore(args.out / "seen.json")
    result = run(
        FederalRegisterSource(),
        keywords=args.keyword,
        since=since,
        max_records=args.max_records,
        seen=seen,
    )
    append_csv(args.out / "records.csv", result.new_records)
    (args.out / "digest.md").write_text(
        digest_markdown(result.new_records, title=f"New records since {since}"), encoding="utf-8"
    )
    seen.flush()  # only after outputs are written, so a failed run is retried next time
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
