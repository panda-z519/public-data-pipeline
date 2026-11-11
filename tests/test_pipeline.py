from pathlib import Path

import httpx
import pytest

from data_pipeline import cli
from data_pipeline.pipeline import SeenStore, append_csv, digest_markdown, run
from data_pipeline.sources.federal_register import API_URL, FederalRegisterSource

PAGE_1 = {
    "count": 3,
    "next_page_url": "https://www.federalregister.gov/api/v1/documents.json?page=2",
    "results": [
        {
            "document_number": "2026-00001",
            "title": "Rule  on\nAI systems",
            "type": "Rule",
            "abstract": "Sets   requirements.",
            "html_url": "https://example.test/1",
            "publication_date": "2026-11-02",
            "agencies": [{"name": "Commerce Department"}, {"raw_name": "NIST"}],
        },
        {"title": "missing id is skipped"},
    ],
}
PAGE_2 = {
    "count": 3,
    "next_page_url": None,
    "results": [
        {
            "document_number": "2026-00002",
            "title": "Notice",
            "type": "Notice",
            "html_url": "https://example.test/2",
            "publication_date": "2026-11-03",
            "agencies": [],
        }
    ],
}


def _source(handler) -> FederalRegisterSource:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return FederalRegisterSource(client, polite_delay_seconds=0)


def _paged_handler(seen_requests: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, json=PAGE_2 if "page=2" in str(request.url) else PAGE_1)

    return handler


def test_fetch_follows_pages_normalizes_and_skips_bad_items() -> None:
    requests: list[httpx.Request] = []
    records = list(
        _source(_paged_handler(requests)).fetch(
            keywords=["AI", "machine learning"], since="2026-11-01", max_records=10
        )
    )
    assert [r.record_id for r in records] == ["2026-00001", "2026-00002"]
    first = records[0]
    assert first.title == "Rule on AI systems"
    assert first.summary == "Sets requirements."
    assert first.organizations == ("Commerce Department", "NIST")
    query = requests[0].url.params
    assert str(requests[0].url).startswith(API_URL)
    assert query["conditions[term]"] == '"AI" | "machine learning"'
    assert query["conditions[publication_date][gte]"] == "2026-11-01"
    assert "agencies" in query.get_list("fields[]")


def test_max_records_stops_early_without_fetching_next_page() -> None:
    requests: list[httpx.Request] = []
    records = list(
        _source(_paged_handler(requests)).fetch(keywords=[], since="2026-11-01", max_records=1)
    )
    assert len(records) == 1
    assert len(requests) == 1


def test_retries_server_errors_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr("data_pipeline.sources.federal_register.time.sleep", lambda _: None)
    statuses = iter([503, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        return httpx.Response(status, json=PAGE_2 if status == 200 else {})

    records = list(_source(handler).fetch(keywords=[], since="2026-11-01", max_records=5))
    assert [r.record_id for r in records] == ["2026-00002"]


def test_client_errors_are_not_retried(monkeypatch) -> None:
    monkeypatch.setattr("data_pipeline.sources.federal_register.time.sleep", lambda _: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={})

    with pytest.raises(httpx.HTTPStatusError):
        list(_source(handler).fetch(keywords=[], since="2026-11-01", max_records=5))
    assert calls["n"] == 1


def test_second_run_only_returns_new_records(tmp_path: Path) -> None:
    seen = SeenStore(tmp_path / "seen.json")
    source = _source(_paged_handler([]))
    first = run(source, keywords=[], since="2026-11-01", max_records=10, seen=seen)
    seen.flush()
    again = run(
        source,
        keywords=[],
        since="2026-11-01",
        max_records=10,
        seen=SeenStore(tmp_path / "seen.json"),
    )
    assert len(first.new_records) == 2
    assert again.fetched == 2
    assert again.new_records == []


def test_csv_and_digest(tmp_path: Path) -> None:
    records = list(
        _source(_paged_handler([])).fetch(keywords=[], since="2026-11-01", max_records=10)
    )
    assert append_csv(tmp_path / "out.csv", records) == 2
    append_csv(tmp_path / "out.csv", records[:1])
    lines = (tmp_path / "out.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4  # header written once
    digest = digest_markdown(records, title="Weekly")
    assert "2 new item(s)." in digest
    assert "[Rule on AI systems](https://example.test/1) (Commerce Department, NIST)" in digest


def test_cli_does_not_mark_seen_when_export_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        cli, "FederalRegisterSource", lambda: _source(_paged_handler([]))
    )

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(cli, "append_csv", boom)
    with pytest.raises(OSError):
        cli.main(["--out", str(tmp_path)])
    assert not (tmp_path / "seen.json").exists()
