# Public Data Pipeline

Collects new public records on a schedule and delivers only what changed: a clean CSV
(ready for Google Sheets or Airtable) plus a short Markdown digest you can email or post
to Slack. The first source is the US Federal Register, so it works as a regulation
monitor out of the box ("tell me every new rule or notice that mentions AI").

```
Federal Register API ──► normalize ──► de-duplicate (remembers past runs) ──► CSV + digest
```

## Why it is built this way

- **Only new items.** Record ids are remembered between runs, so a weekly job never sends
  the same item twice. State is saved only after outputs are written, so a failed run is
  simply retried next time.
- **Polite and resilient.** Pages are followed automatically with a short delay; rate limits
  and server errors are retried a bounded number of times; client errors fail fast.
- **No paid infrastructure.** The source is a free official API that needs no key and no
  proxy.
- **Pluggable sources.** Every source yields the same `Record` shape, so adding a new one
  does not touch the export code.

## Run it

```bash
uv sync
uv run data-pipeline --keyword "artificial intelligence" --days 7
# output/records.csv, output/digest.md
uv run pytest
```

Schedule it with cron, GitHub Actions or n8n. It also ships as an Apify Actor
(`.actor/`), where each record is a pay-per-event result.
