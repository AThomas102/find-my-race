"""Argparse entrypoints for the modular ingest stack."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from fmr_core.field_stats import field_summary_stats_from_equiv_5k
from fmr_core.models import FieldSummary, Race

from ingest.field.summary import raw_results_to_field_summary
from ingest.models import RawResultRow
from ingest.pipeline import merge_race_json_files, run_ingest, write_races_json
from ingest.sources import get_detail_source, get_listing_source


def _cmd_list(args: argparse.Namespace) -> int:
    src = get_listing_source(args.source, args.config)
    rows = src.list_races()
    json.dump([asdict(r) for r in rows], sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_ingest_sample(args: argparse.Namespace) -> int:
    listing = get_listing_source(args.source, args.config)
    detail = get_detail_source(args.source)
    races = run_ingest(listing, detail)
    out = Path(args.out)
    if args.merge and out.exists():
        merged = merge_race_json_files(out, races)
        write_races_json(out, merged)
    else:
        write_races_json(out, races)
    print(f"Wrote {len(races)} race(s) → {out}", file=sys.stderr)
    return 0


def _cmd_merge_field_summary(args: argparse.Namespace) -> int:
    prov = args.provenance
    equiv: list[float] = []
    if args.equiv_file:
        raw = json.loads(Path(args.equiv_file).read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            print("--equiv-file must contain a JSON array of numbers", file=sys.stderr)
            return 2
        summary = field_summary_stats_from_equiv_5k(equiv)
        summary["provenance"] = prov
    elif args.results_file:
        raw = json.loads(Path(args.results_file).read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            print("--results-file must contain a JSON array of objects", file=sys.stderr)
            return 2
        rows = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                rows.append(
                    RawResultRow(
                        distance_m=int(item["distance_m"]),
                        time_sec=float(item["time_sec"]),
                        source_tag=item.get("source_tag"),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        summary = raw_results_to_field_summary(rows, provenance=prov)
    else:
        print("Provide --equiv-file or --results-file", file=sys.stderr)
        return 2

    if not args.patch_race_json or not args.race_id:
        json.dump(summary, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    path = Path(args.patch_race_json)
    raw_list = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_list, list):
        print(f"{path} must contain a JSON array", file=sys.stderr)
        return 2
    out_races: list[Race] = []
    found = False
    for item in raw_list:
        r = Race.model_validate(item)
        if r.id == args.race_id:
            base = r.field_summary.model_dump() if r.field_summary else {}
            base.update(summary)
            r = r.model_copy(update={"field_summary": FieldSummary.model_validate(base)})
            found = True
        out_races.append(r)
    if not found:
        print(f"race_id {args.race_id!r} not found in {path}", file=sys.stderr)
        return 3
    write_races_json(path, out_races)
    print(f"Updated field_summary on {args.race_id!r} in {path}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Find My Race — modular ingest / field-summary CLI")
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("list", help="Run listing source and print RawRaceRecord JSON")
    pl.add_argument(
        "--source",
        required=True,
        choices=["curated", "curated_json", "seed-ldjson"],
        help="curated / curated_json: local JSON races[] (see data/ingest_seeds/curated_races.sample.json)",
    )
    pl.add_argument("--config", required=True, help="Source-specific JSON config path")
    pl.set_defaults(func=_cmd_list)

    pi = sub.add_parser("ingest-sample", help="List → detail → Race JSON file")
    pi.add_argument(
        "--source",
        required=True,
        choices=["curated", "curated_json", "seed-ldjson"],
    )
    pi.add_argument("--config", required=True)
    pi.add_argument("--out", required=True, help="Output JSON array path (e.g. data/races/import_demo.json)")
    pi.add_argument(
        "--merge",
        action="store_true",
        help="Merge with existing JSON at --out by race id (later wins)",
    )
    pi.set_defaults(func=_cmd_ingest_sample)

    pm = sub.add_parser(
        "merge-field-summary",
        help="Build FieldSummary JSON from equiv 5K list or raw results; optionally patch a race file",
    )
    pm.add_argument(
        "--provenance",
        choices=["past_results", "entrants", "estimated", "unknown"],
        default="unknown",
    )
    pm.add_argument("--equiv-file", help="JSON array of equivalent 5K seconds (already converted)")
    pm.add_argument(
        "--results-file",
        help='JSON array of {"distance_m": 10000, "time_sec": 2400} rows',
    )
    pm.add_argument("--patch-race-json", help="Race JSON array file to update in-place")
    pm.add_argument("--race-id", help="Race id within that file to attach field_summary to")
    pm.set_defaults(func=_cmd_merge_field_summary)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))
