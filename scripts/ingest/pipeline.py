"""Compose sources → :class:`fmr_core.models.Race` → JSON on disk."""

from __future__ import annotations

import json
import re
import warnings
from datetime import date, datetime
from pathlib import Path

from fmr_core.models import CourseProfile, Race

from ingest.models import IngestError, RawRaceRecord
from ingest.sources.base import RaceDetailSource, RaceListingSource

_PLACEHOLDER_SOURCE_PAGES = frozenset({"stub://local", "curated-json://local"})


def _slug(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:48] or "race"


def _race_id_for_record(rec: RawRaceRecord) -> str:
    short = rec.external_key[:16] if len(rec.external_key) >= 16 else rec.external_key
    slug = _slug(rec.title or "event")
    return f"ing-{rec.source_id}-{slug}-{short}"


def _parse_start(raw: str | None) -> date | datetime:
    if not raw:
        raise ValueError("missing start")
    s = raw.strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return date.fromisoformat(s[:10])


def record_to_race(rec: RawRaceRecord) -> Race:
    start = _parse_start(rec.start_raw)
    loc = rec.place_name or rec.address_text
    sign_up = rec.event_url or (
        rec.source_page_url if rec.source_page_url not in _PLACEHOLDER_SOURCE_PAGES else None
    )
    course = CourseProfile()
    if rec.course_distance_m is not None:
        course.distance_m = int(rec.course_distance_m)

    meta = {
        "ingest_source": rec.source_id,
        "ingest_external_key": rec.external_key,
        "source_page_url": rec.source_page_url,
        **rec.extra,
    }
    if rec.description:
        meta["description_snippet"] = rec.description[:500]

    return Race(
        id=_race_id_for_record(rec),
        title=(rec.title or "Untitled event").strip(),
        start=start,
        region=rec.region,
        country=rec.country,
        location_label=loc,
        coordinates=None,
        course=course,
        field_summary=None,
        sign_up_url=sign_up,
        metadata=meta,
    )


def records_to_races(records: list[RawRaceRecord]) -> list[Race]:
    out: list[Race] = []
    for rec in records:
        try:
            out.append(record_to_race(rec))
        except (ValueError, IngestError) as e:
            warnings.warn(f"skip record {rec.external_key!r}: {e}", stacklevel=1)
        except Exception as e:
            warnings.warn(f"skip record {rec.external_key!r}: unexpected {e!r}", stacklevel=1)
    return out


def run_ingest(
    listing: RaceListingSource,
    detail: RaceDetailSource | None = None,
) -> list[Race]:
    rows = listing.list_races()
    if detail is not None:
        rows = [detail.enrich(r) for r in rows]
    return records_to_races(rows)


def _load_races_file(path: Path) -> list[Race]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected JSON array in {path}")
    return [Race.model_validate(x) for x in raw]


def merge_race_json_files(target: Path, incoming: list[Race]) -> list[Race]:
    merged: dict[str, Race] = {}
    for r in _load_races_file(target):
        merged[r.id] = r
    for r in incoming:
        merged[r.id] = r
    return list(merged.values())


def write_races_json(path: Path, races: list[Race]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.model_dump(mode="json") for r in sorted(races, key=lambda x: x.id)]
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
