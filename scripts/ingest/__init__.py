"""
Modular race-ingestion pipeline (listing → detail → ``fmr_core.models.Race`` → JSON files).

**How to add a new source**

1. Implement :class:`ingest.sources.base.RaceListingSource` (and optionally
   :class:`ingest.sources.base.RaceDetailSource`) in ``sources/your_site.py``.
2. Register the implementation in :data:`ingest.sources.SOURCE_REGISTRY` (see ``sources/__init__.py``).
3. Prefer **curated seed lists** (URLs or ICS links in JSON) over unbounded crawling; respect
   ``robots.txt`` and site terms; do not bypass CAPTCHAs.
4. Map site-specific rows to :class:`ingest.models.RawRaceRecord`, then run
   :func:`ingest.pipeline.records_to_races` so normalization stays centralized.

**Field / handicap data**

Official results → finish times → equivalent 5K (via :func:`fmr_core.handicap.equivalent_5k_seconds`
after validation) → aggregate with :mod:`fmr_core.field_stats`. Full accuracy needs parsed result
lists; optional athlete-ID → Po10 mapping is a future module (see ``AGENTS.md``).

**CLI**

Run from repo root: ``python scripts/run_ingest.py --help``
"""

from ingest.pipeline import merge_race_json_files, run_ingest, write_races_json

__all__ = ["merge_race_json_files", "run_ingest", "write_races_json"]
