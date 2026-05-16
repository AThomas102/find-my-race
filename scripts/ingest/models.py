"""Internal DTOs for the ingest pipeline (not the public API schema)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class IngestError(Exception):
    """Recoverable or fatal ingest problem; wrap underlying cause when useful."""

    def __init__(self, message: str, *, code: str = "ingest_error", cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.cause = cause


@dataclass
class RawRaceRecord:
    """One discovered race before normalization to :class:`fmr_core.models.Race`."""

    source_id: str
    external_key: str
    title: str | None
    start_raw: str | None
    source_page_url: str
    end_raw: str | None = None
    place_name: str | None = None
    address_text: str | None = None
    event_url: str | None = None
    description: str | None = None
    country: str = "GB"
    region: str | None = None
    course_distance_m: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawResultRow:
    """Minimal finish-line row for field statistics (no names — avoid storing scraped PII here)."""

    distance_m: int
    time_sec: float
    source_tag: str | None = None
