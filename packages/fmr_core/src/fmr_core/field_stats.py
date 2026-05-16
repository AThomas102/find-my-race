"""Pure aggregation of equivalent 5K samples into ``FieldSummary``-compatible numbers."""

from __future__ import annotations

import statistics
from typing import Any


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return d0 + d1


def field_summary_stats_from_equiv_5k(values: list[float]) -> dict[str, Any]:
    """
    Median and quartiles of equivalent 5K performances (seconds, lower = faster).

    Returns keys aligned with ``FieldSummary`` numeric fields (no ``provenance``).
    """
    xs = sorted(float(x) for x in values if x == x and x > 0)
    if not xs:
        return {
            "median_5k_sec": None,
            "p25_5k_sec": None,
            "p75_5k_sec": None,
            "sample_size": 0,
        }
    return {
        "median_5k_sec": statistics.median(xs),
        "p25_5k_sec": _percentile(xs, 0.25),
        "p75_5k_sec": _percentile(xs, 0.75),
        "sample_size": len(xs),
    }
