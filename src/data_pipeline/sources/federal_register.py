"""US Federal Register public API: free, official, no API key and no proxy needed.

Docs: https://www.federalregister.gov/developers/documentation/api/v1
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any

import httpx

from data_pipeline.models import Record

logger = logging.getLogger(__name__)

API_URL = "https://www.federalregister.gov/api/v1/documents.json"
_FIELDS = [
    "document_number",
    "title",
    "type",
    "abstract",
    "html_url",
    "publication_date",
    "agencies",
]
_RETRYABLE = {429, 500, 502, 503, 504}


class FederalRegisterSource:
    name = "federal_register"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        page_size: int = 100,
        max_attempts: int = 3,
        polite_delay_seconds: float = 0.5,
    ) -> None:
        self._client = client or httpx.Client(timeout=30, headers={"User-Agent": "data-pipeline"})
        self._page_size = page_size
        self._max_attempts = max_attempts
        self._delay = polite_delay_seconds

    def fetch(self, *, keywords: list[str], since: str, max_records: int) -> Iterator[Record]:
        params: dict[str, Any] = {
            "per_page": self._page_size,
            "order": "newest",
            "conditions[publication_date][gte]": since,
            "fields[]": _FIELDS,
        }
        if keywords:
            params["conditions[term]"] = " | ".join(f'"{k}"' for k in keywords)
        url: str | None = API_URL
        query: dict[str, Any] | None = params
        emitted = 0
        while url and emitted < max_records:
            payload = self._get(url, query)
            for item in payload.get("results", []):
                record = _to_record(item)
                if record is None:
                    continue
                yield record
                emitted += 1
                if emitted >= max_records:
                    return
            # next_page_url already carries every query parameter. Passing params here,
            # even an empty dict, would make httpx drop that query string.
            url, query = payload.get("next_page_url"), None
            if url:
                time.sleep(self._delay)

    def _get(self, url: str, params: dict[str, Any] | None) -> dict[str, Any]:
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.get(url, params=params)
            except httpx.TransportError:
                if attempt == self._max_attempts:
                    raise
                time.sleep(2 ** (attempt - 1))
                continue
            if response.status_code in _RETRYABLE and attempt < self._max_attempts:
                logger.warning("retrying status=%s attempt=%s", response.status_code, attempt)
                time.sleep(2 ** (attempt - 1))
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("unreachable")


def _to_record(item: dict[str, Any]) -> Record | None:
    doc_id = item.get("document_number")
    title = item.get("title")
    if not doc_id or not title:
        logger.warning("skipping malformed item keys=%s", sorted(item))
        return None
    agencies = tuple(
        a.get("name") or a.get("raw_name") or "" for a in item.get("agencies") or []
    )
    return Record(
        source=FederalRegisterSource.name,
        record_id=str(doc_id),
        title=" ".join(str(title).split()),
        published_on=str(item.get("publication_date") or ""),
        url=str(item.get("html_url") or ""),
        record_type=str(item.get("type") or ""),
        organizations=tuple(a for a in agencies if a),
        summary=" ".join(str(item.get("abstract") or "").split()),
    )
