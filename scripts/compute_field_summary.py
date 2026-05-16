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
import sys
from typing import Any

from fmr_core.field_stats import field_summary_stats_from_equiv_5k


def summarize(values: list[float]) -> dict[str, Any]:
    return field_summary_stats_from_equiv_5k(values)


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
