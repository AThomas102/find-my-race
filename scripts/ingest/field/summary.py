"""
Field-strength helpers for ingest — equivalent 5K mapping + aggregation.

Uses :func:`fmr_core.handicap.equivalent_5k_seconds` only after inputs pass core validation.
For production field summaries you still want **official results** (times + distances), then
optional athlete ID / Po10 mapping in a separate future step; see module docstring in
``scripts/ingest/__init__.py``.
"""

from __future__ import annotations

from typing import Literal

from fmr_core.field_stats import field_summary_stats_from_equiv_5k
from fmr_core.handicap import equivalent_5k_seconds

from ingest.models import RawResultRow

Provenance = Literal["past_results", "entrants", "estimated", "unknown"]


def equiv_5k_for_result(row: RawResultRow) -> float | None:
    try:
        return equivalent_5k_seconds(int(row.distance_m), float(row.time_sec))
    except ValueError:
        return None


def raw_results_to_field_summary(
    rows: list[RawResultRow],
    *,
    provenance: Provenance = "unknown",
) -> dict:
    equiv = [x for r in rows if (x := equiv_5k_for_result(r)) is not None]
    out = field_summary_stats_from_equiv_5k(equiv)
    out["provenance"] = provenance
    return out
