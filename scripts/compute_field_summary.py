#!/usr/bin/env python3
"""
Derive Race.field_summary-style stats from a list of equivalent 5K performances (seconds).

Typical upstreams:
  - Parsed official race results mapped to athlete records
  - Output of `powerof10_athlete_scraper.py --flatten-performances` feeding a resolver
    that extracts best-effort distances/times → equivalent_5k_seconds (fmr_core.handicap).

This CLI stays intentionally small so agents extend the ingestion side without touching scoring.

Examples:
  echo '[1500, 1550, 1600]' | python compute_field_summary.py --stdin-json
  python compute_field_summary.py --from-file equiv_list.json --provenance past_results
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
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


def summarize(values: list[float]) -> dict[str, Any]:
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


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Compute FieldSummary-style stats from equivalent 5K seconds.")
    p.add_argument("--stdin-json", action="store_true", help="Read JSON array of numbers from stdin")
    p.add_argument("--from-file", metavar="PATH", help="JSON file: array of numbers")
    p.add_argument(
        "--provenance",
        choices=["past_results", "entrants", "estimated", "unknown"],
        default="unknown",
    )
    args = p.parse_args(argv)

    raw: Any
    if args.stdin_json:
        raw = json.load(sys.stdin)
    elif args.from_file:
        with open(args.from_file, encoding="utf-8") as f:
            raw = json.load(f)
    else:
        p.error("Provide --stdin-json or --from-file")

    if not isinstance(raw, list):
        print("Expected JSON array of numeric equivalent 5K seconds", file=sys.stderr)
        return 2

    stats_obj = summarize([float(x) for x in raw])
    stats_obj["provenance"] = args.provenance
    json.dump(stats_obj, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
