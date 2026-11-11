"""Apify Actor entry point. Same pipeline, but output goes to the Actor dataset.

Pricing is pay-per-event: one "result" event per record pushed, so the price per record
must cover platform costs. This source needs no proxy, which keeps that cost low.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from apify import Actor

from data_pipeline.sources.federal_register import FederalRegisterSource

MAX_RECORDS_CAP = 5_000


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        keywords = [k for k in actor_input.get("keywords", []) if isinstance(k, str) and k]
        days = max(1, min(int(actor_input.get("daysBack", 7)), 365))
        max_records = max(1, min(int(actor_input.get("maxRecords", 100)), MAX_RECORDS_CAP))
        since = (date.today() - timedelta(days=days)).isoformat()

        source = FederalRegisterSource()
        records = await asyncio.to_thread(
            lambda: list(source.fetch(keywords=keywords, since=since, max_records=max_records))
        )
        for record in records:
            # Charges only when the Actor runs with pay-per-event pricing.
            await Actor.push_data(record.to_row(), charged_event_name="result")
        await Actor.set_status_message(f"Saved {len(records)} records since {since}")


if __name__ == "__main__":
    asyncio.run(main())
