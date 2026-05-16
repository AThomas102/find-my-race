"""
Thin adapter: curated page URLs → JSON-LD / Event rows via the existing UK crawl helpers.

Network access is **opt-in** via environment variable ``FMR_ALLOW_NETWORK_INGEST=1`` so
default runs stay safe/offline. When disallowed, :meth:`list_races` returns an empty list.

Requires: ``requests``, ``beautifulsoup4`` (see ``scripts/requirements-ingest.txt``).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from ingest.models import RawRaceRecord
from ingest.sources.base import RaceListingSource


class SeedLdjsonListingSource:
    def __init__(self, config_path: str | Path) -> None:
        self._path = Path(config_path)
        cfg = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            raise ValueError("seed-ldjson config must be a JSON object")
        urls = cfg.get("urls") or []
        if not isinstance(urls, list):
            raise ValueError("'urls' must be an array of strings")
        self._urls = [str(u) for u in urls]
        self._uk_only = bool(cfg.get("uk_only", False))
        self._delay_s = float(cfg.get("delay_s", 1.0))
        self._user_agent = str(
            cfg.get("user_agent")
            or "find-my-race-ingest/1.0 (+https://example.local; research; respect robots.txt)"
        )
        self._max_pages = int(cfg.get("max_pages", len(self._urls) or 1))

    def list_races(self) -> list[RawRaceRecord]:
        if os.environ.get("FMR_ALLOW_NETWORK_INGEST", "").strip() != "1":
            print(
                "seed-ldjson: skipping network fetch (set FMR_ALLOW_NETWORK_INGEST=1 to enable).",
                file=sys.stderr,
            )
            return []

        from uk_running_events_crawl import (
            CrawlConfig,
            FetchStats,
            RobotsCache,
            extract_events_from_html,
            fetch_html,
            row_content_key,
        )

        cfg = CrawlConfig(
            delay_s=self._delay_s,
            user_agent=self._user_agent,
            max_pages=self._max_pages,
            uk_only=self._uk_only,
        )
        robots = RobotsCache()
        stats = FetchStats()
        rows: list[dict[str, Any]] = []
        for url in self._urls[: self._max_pages]:
            html = fetch_html(url, cfg, robots, stats)
            if not html:
                continue
            rows.extend(extract_events_from_html(html, url, cfg.uk_only))

        out: list[RawRaceRecord] = []
        for r in rows:
            ck = row_content_key(r)
            out.append(_crawl_dict_to_raw(ck, r))
        return out


def _crawl_dict_to_raw(content_key: str, r: dict[str, Any]) -> RawRaceRecord:
    return RawRaceRecord(
        source_id="seed-ldjson",
        external_key=content_key,
        title=r.get("title"),
        start_raw=r.get("start"),
        source_page_url=str(r.get("source_page_url") or ""),
        end_raw=r.get("end"),
        place_name=r.get("place_name"),
        address_text=r.get("address_text"),
        event_url=r.get("event_url"),
        description=r.get("description"),
        country="GB",
        extra={"source_kind": r.get("source_kind"), "sport": r.get("sport")},
    )
