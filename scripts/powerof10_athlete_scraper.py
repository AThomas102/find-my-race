#!/usr/bin/env python3
"""
Fetch athlete profiles from https://www.powerof10.uk/ for offline / DB use.

Important constraints discovered when building this:

- Athlete profiles use UUID paths: /Home/Athlete/<uuid>
- Each profile page embeds a JSON blob (`let gridData = {...};`) with Track / Road / XC
  performances plus summary fields (clubs, age groups).
- Site search and rankings JSON endpoints return RECAPTCHA_REQUIRED for unattended HTTP
  clients; bulk discovery via those APIs needs a browser solving reCAPTCHA or manual exports.

This script focuses on what works reliably without bypassing protections:

- Fetch one or many athlete pages by UUID (from URLs or an id list file).
- Optional: club name autocomplete (ClubNameAutoComplete) returns club names + UUID refs.
- Optional: scan local HTML files for Po10 athlete URLs (e.g. pages saved from a browser).

Respect Po10's Terms of Use, cache responses where possible, and use modest rate limits.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

BASE = "https://www.powerof10.uk"
DEFAULT_UA = (
    "Po10AthleteScraper/1.0 (+local research; honour robots/terms and rate limits)"
)


@dataclass
class FetchResult:
    status_code: int | None = None
    body: str = ""
    error: str | None = None


def fetch_text(url: str, *, timeout: float, user_agent: str) -> FetchResult:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            raw = resp.read()
            return FetchResult(status_code=resp.status, body=raw.decode(charset, errors="replace"))
    except urllib.error.HTTPError as e:
        charset = e.headers.get_content_charset() if e.headers else None
        raw = e.read() if e.fp else b""
        body = raw.decode(charset or "utf-8", errors="replace")
        return FetchResult(status_code=e.code, body=body, error=str(e))
    except Exception as e:  # noqa: BLE001 — surface network failures cleanly
        return FetchResult(error=str(e))


_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)


def athlete_urls_from_text(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in _UUID_RE.finditer(text):
        start = m.start()
        if start >= 5 and text[start - 8 : start].lower().endswith("/athlete/"):
            u = m.group(0).lower()
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


def normalize_athlete_id(raw: str) -> str | None:
    s = raw.strip()
    if "/Home/Athlete/" in s:
        s = s.split("/Home/Athlete/", 1)[-1]
    s = s.split("?", 1)[0].strip("/ ")
    if _UUID_RE.fullmatch(s):
        return s.lower()
    return None


def extract_between(html: str, start_pat: str, end_pat: str) -> str | None:
    i = html.find(start_pat)
    if i < 0:
        return None
    i += len(start_pat)
    j = html.find(end_pat, i)
    if j < 0:
        return None
    return html[i:j]


def parse_grid_data(html: str) -> dict[str, Any] | None:
    blob = extract_between(html, "let gridData = ", "gridSearchRun")
    if blob is None:
        return None
    blob = blob.strip().rstrip(";").strip()
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def _clean_inline_html_fragment(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def parse_profile(html: str) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "first_name": None,
        "surname": None,
        "sex": None,
        "age_group_track": None,
        "age_group_road": None,
        "age_group_xc": None,
        "age_years_note": None,
        "club": None,
        "county": None,
        "region": None,
        "home_nation": None,
        "lead_coaches": [],
    }

    m_name = re.search(r'<div class="name">\s*([^<]+)', html)
    m_sn = re.search(r'<div class="surname">\s*([^<]+)', html)
    if m_name:
        profile["first_name"] = _clean_inline_html_fragment(m_name.group(1))
    if m_sn:
        profile["surname"] = _clean_inline_html_fragment(m_sn.group(1))

    m_sex = re.search(r"SEX\s*<br\s*/>\s*<strong>\s*([^<]+)", html, re.I)
    if m_sex:
        profile["sex"] = _clean_inline_html_fragment(m_sex.group(1))

    for label, key in (
        ('<span id="divTrackAgeGroup"', "age_group_track"),
        ('<span id="divRoadAgeGroup"', "age_group_road"),
        ('<span id="divXcAgeGroup"', "age_group_xc"),
    ):
        m = re.search(label + r'[^>]*>([^<]*)</span>', html)
        if m:
            profile[key] = _clean_inline_html_fragment(m.group(1))

    m_yrs = re.search(r"\(\s*(\d+)\s*YRS\s*\)", html, re.I)
    if m_yrs:
        profile["age_years_note"] = int(m_yrs.group(1))

    m_club = re.search(
        r'<p class="club">\s*CLUB.*?href="/Home/Club/(' + _UUID_RE.pattern + r')"[^>]*>\s*([^<]+)',
        html,
        re.I | re.S,
    )
    if m_club:
        profile["club"] = {"id": m_club.group(1).lower(), "name": _clean_inline_html_fragment(m_club.group(2))}

    for lbl, key in (
        ("COUNTY", "county"),
        ("REGION", "region"),
        ("HOME NATION", "home_nation"),
    ):
        m = re.search(lbl + r"\s*<br\s*/>\s*<strong>\s*([^<]+)", html)
        if m:
            profile[key] = _clean_inline_html_fragment(m.group(1))

    coaches: list[dict[str, str]] = []
    for m in re.finditer(
        r'LEAD COACH.*?href="/Home/Coach/(' + _UUID_RE.pattern + r')"[^>]*>\s*<strong>\s*([^<]+)',
        html,
        re.I | re.S,
    ):
        coaches.append({"id": m.group(1).lower(), "name": _clean_inline_html_fragment(m.group(2))})
    profile["lead_coaches"] = coaches

    return profile


def athlete_page_summary(html: str, athlete_id: str, url: str) -> dict[str, Any]:
    missing = "could not be found" in html.lower()
    ref_m = re.search(r"athleteRef:\s*'(" + _UUID_RE.pattern + r")'", html, re.I)
    embedded_ref = ref_m.group(1).lower() if ref_m else None

    grid = None if missing else parse_grid_data(html)

    return {
        "athlete_id": athlete_id,
        "profile_url": url,
        "missing_on_site": missing,
        "embedded_athlete_ref": embedded_ref,
        "profile": {} if missing else parse_profile(html),
        "performance_bundle": grid,
    }


def clubs_autocomplete(prefix: str, *, timeout: float, user_agent: str) -> list[dict[str, str]]:
    q = urllib.parse.urlencode({"clubPrefix": prefix})
    url = f"{BASE}/Home/ClubNameAutoComplete?{q}"
    res = fetch_text(url, timeout=timeout, user_agent=user_agent)
    if res.error and res.body == "":
        raise RuntimeError(res.error)
    try:
        data = json.loads(res.body)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Club autocomplete JSON decode failed: {e}") from e
    out = []
    for row in data:
        dis = row.get("Dis")
        ref = row.get("Ref")
        if isinstance(dis, str) and isinstance(ref, str):
            out.append({"name": dis, "club_ref": ref.lower()})
    return out


def collect_performance_rows(bundle: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not bundle or "perfs" not in bundle:
        return []
    rows: list[dict[str, Any]] = []
    dictpgs = bundle["perfs"].get("dictpgs") or {}
    for discipline, block in dictpgs.items():
        for pg in block.get("pgs") or []:
            for r in pg.get("results") or []:
                item = dict(r)
                item["_discipline"] = discipline
                rows.append(item)
    return rows


@dataclass
class CliConfig:
    athlete_inputs: list[str] = field(default_factory=list)
    ids_file: str | None = None
    club_prefix: str | None = None
    extract_urls_from: list[str] = field(default_factory=list)
    delay_s: float = 1.0
    timeout: float = 30.0
    user_agent: str = DEFAULT_UA
    flatten_performances: bool = False
    output_path: str | None = None


def load_ids(cfg: CliConfig) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        aid = normalize_athlete_id(raw)
        if aid and aid not in seen:
            seen.add(aid)
            ids.append(aid)

    for x in cfg.athlete_inputs:
        add(x)
    if cfg.ids_file:
        with open(cfg.ids_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    add(line)
    for path in cfg.extract_urls_from:
        with open(path, encoding="utf-8") as f:
            for u in athlete_urls_from_text(f.read()):
                add(u)
    return ids


def run(cfg: CliConfig) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    if cfg.club_prefix:
        clubs = clubs_autocomplete(cfg.club_prefix, timeout=cfg.timeout, user_agent=cfg.user_agent)
        records.append({"_kind": "club_autocomplete", "prefix": cfg.club_prefix, "clubs": clubs})

    ids = load_ids(cfg)
    for i, aid in enumerate(ids):
        url = f"{BASE}/Home/Athlete/{aid}"
        res = fetch_text(url, timeout=cfg.timeout, user_agent=cfg.user_agent)
        base_rec: dict[str, Any] = {
            "athlete_id": aid,
            "profile_url": url,
            "http_status": res.status_code,
            "fetch_error": res.error,
        }
        if res.error and not res.body:
            records.append(base_rec)
        else:
            summary = athlete_page_summary(res.body, aid, url)
            if cfg.flatten_performances and summary.get("performance_bundle"):
                perf_rows = collect_performance_rows(summary["performance_bundle"])
                summary["performances_flat"] = perf_rows
                summary.pop("performance_bundle", None)
            summary.update({k: v for k, v in base_rec.items() if k in ("http_status", "fetch_error")})
            records.append(summary)

        if cfg.delay_s > 0 and i + 1 < len(ids):
            time.sleep(cfg.delay_s)

    return records


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Collect Po10 athlete data for database seeding.")
    p.add_argument(
        "--athlete",
        action="append",
        default=[],
        help="Athlete UUID or full profile URL (repeatable)",
    )
    p.add_argument("--ids-file", help="Text file: one athlete UUID or URL per line (# comments ok)")
    p.add_argument(
        "--club-prefix",
        metavar="PREFIX",
        help="Query club autocomplete (min length 3 on site UI); prints matching clubs",
    )
    p.add_argument(
        "--extract-urls-from-html",
        action="append",
        default=[],
        metavar="PATH",
        help="Scan saved HTML for /Home/Athlete/<uuid> links (repeatable)",
    )
    p.add_argument("--delay", type=float, default=1.0, help="Seconds between athlete requests (default 1)")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--user-agent", default=DEFAULT_UA)
    p.add_argument(
        "--flatten-performances",
        action="store_true",
        help="Replace embedded performance_bundle with performances_flat rows",
    )
    p.add_argument("-o", "--output", help="Write JSON array to this file (UTF-8)")
    args = p.parse_args(argv)

    cfg = CliConfig(
        athlete_inputs=list(args.athlete),
        ids_file=args.ids_file,
        club_prefix=args.club_prefix,
        extract_urls_from=list(args.extract_urls_from_html),
        delay_s=max(0.0, args.delay),
        timeout=args.timeout,
        user_agent=args.user_agent,
        flatten_performances=args.flatten_performances,
        output_path=args.output,
    )

    if (
        not cfg.athlete_inputs
        and not cfg.ids_file
        and not cfg.club_prefix
        and not cfg.extract_urls_from
    ):
        p.error("Provide --athlete, --ids-file, --club-prefix, and/or --extract-urls-from-html")

    records = run(cfg)
    text = json.dumps(records, indent=2, ensure_ascii=False)
    if cfg.output_path:
        with open(cfg.output_path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
