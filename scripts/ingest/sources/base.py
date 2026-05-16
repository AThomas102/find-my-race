"""
Source interfaces for race discovery.

**How to add a new source**

1. Define a small class implementing :class:`RaceListingSource` (required).
2. If listing URLs are shallow, implement :class:`RaceDetailSource` to fetch HTML/API pages.
3. Emit :class:`ingest.models.RawRaceRecord` rows with a stable ``external_key`` per event.
4. Register constructors in ``ingest.sources.SOURCE_REGISTRY`` / ``DETAIL_REGISTRY``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ingest.models import RawRaceRecord


@runtime_checkable
class RaceListingSource(Protocol):
    """Curated or bounded discovery (seed URLs, APIs, local fixtures)."""

    def list_races(self) -> list[RawRaceRecord]:
        """Return zero or more provisional race rows."""
        ...


@runtime_checkable
class RaceDetailSource(Protocol):
    """Fill in or refine a :class:`RawRaceRecord` (optional second pass)."""

    def enrich(self, row: RawRaceRecord) -> RawRaceRecord:
        ...
