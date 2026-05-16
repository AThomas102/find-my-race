"""Load harvested race rows from a local JSON file (no network I/O).

The config file is an object ``{"races": [ ... ]}`` where each item mirrors
fields from :class:`ingest.models.RawRaceRecord` listing shape: paste rows you
already normalised from crawlers or manual copy from official pages.
"""

from __future__ import annotations

import json
from pathlib import Path

from ingest.models import RawRaceRecord
from ingest.sources.base import RaceDetailSource, RaceListingSource

_PLACEHOLDER_SOURCE_PAGE = "curated-json://local"


class CuratedJsonListingSource:
    def __init__(self, config_path: str | Path) -> None:
        self._path = Path(config_path)
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "races" not in raw:
            raise ValueError("Curated JSON config must be an object with a 'races' array")
        self._items = raw["races"]

    def list_races(self) -> list[RawRaceRecord]:
        out: list[RawRaceRecord] = []
        for i, item in enumerate(self._items):
            if not isinstance(item, dict):
                continue
            key = str(item.get("external_key") or f"curated-{i}")
            known = {
                "external_key",
                "title",
                "start",
                "end",
                "source_page_url",
                "place_name",
                "address_text",
                "event_url",
                "description",
                "country",
                "region",
                "course_distance_m",
            }
            extras = {k: v for k, v in item.items() if k not in known}
            out.append(
                RawRaceRecord(
                    source_id="curated_json",
                    external_key=key,
                    title=item.get("title"),
                    start_raw=item.get("start"),
                    source_page_url=str(item.get("source_page_url") or _PLACEHOLDER_SOURCE_PAGE),
                    end_raw=item.get("end"),
                    place_name=item.get("place_name"),
                    address_text=item.get("address_text"),
                    event_url=item.get("event_url"),
                    description=item.get("description"),
                    country=str(item.get("country") or "GB"),
                    region=item.get("region"),
                    course_distance_m=item.get("course_distance_m"),
                    extra=extras,
                )
            )
        return out


class CuratedJsonPassThroughDetail:
    """No-op enrich step (listing row is already complete)."""

    def enrich(self, row: RawRaceRecord) -> RawRaceRecord:
        return row
