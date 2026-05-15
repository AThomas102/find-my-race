#!/usr/bin/env python3
"""
Trawl UK-facing running event pages and emit normalized rows for a race database.

Prioritizes structured data (JSON-LD Event / SportsEvent / ItemList) so one pipeline
works across many sites without maintaining dozens of CSS selectors.

Install dependencies (or use the repo venv at .venv):
  pip install requests beautifulsoup4 icalendar

Usage examples:
  python uk_running_events_crawl.py --seed-urls seeds.txt --out races.jsonl
  python uk_running_events_crawl.py --seed-urls seeds.txt --sqlite races.db
  python uk_running_events_crawl.py --url https://example.com/race-calendar --follow-links --max-pages 30
  python uk_running_events_crawl.py --sitemap https://example.com/sitemap.xml --url-filter race --max-pages 80
  python uk_running_events_crawl.py --ics https://example.com/calendar.ics --uk-only

Notes:
- Respect robots.txt and rate limits; add your own seeds—do not scrape sites that forbid it.
- Many calendars are JavaScript-heavy; those pages need a browser tool or an official API/ICS feed instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.robotparser
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

try:
    from icalendar import Calendar
except ImportError:
    Calendar = None  # type: ignore[misc, assignment]

DEFAULT_UA = (
    "uk-running-events-crawl/1.0 (+https://example.local; research; contact: you@example.com)"
)


@dataclass
class CrawlConfig:
    delay_s: float = 1.0
    timeout_s: float = 25.0
    user_agent: str = DEFAULT_UA
    max_pages: int = 50
    follow_links: bool = False
    url_filter: str | None = None
    uk_only: bool = False


@dataclass
class FetchStats:
    fetched: int = 0
    skipped_robots: int = 0
    errors: int = 0


@dataclass
class RobotsCache:
    parsers: dict[str, urllib.robotparser.RobotFileParser] = field(default_factory=dict)

    def allowed(self, url: str, user_agent: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}/"
        if base not in self.parsers:
            rp = urllib.robotparser.RobotFileParser()
            try:
                rp.set_url(urllib.parse.urljoin(base, "robots.txt"))
                rp.read()
            except OSError:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse([])
            self.parsers[base] = rp
        return self.parsers[base].can_fetch(user_agent, url)


_session: requests.Session | None = None


def _session_get() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


def fetch_html(
    url: str,
    cfg: CrawlConfig,
    robots: RobotsCache,
    stats: FetchStats,
) -> str | None:
    if not robots.allowed(url, cfg.user_agent):
        stats.skipped_robots += 1
        return None
    sess = _session_get()
    try:
        r = sess.get(
            url,
            timeout=cfg.timeout_s,
            headers={"User-Agent": cfg.user_agent, "Accept": "text/html,application/xhtml+xml"},
        )
        stats.fetched += 1
        r.raise_for_status()
        ctype = r.headers.get("Content-Type", "")
        if "text/html" not in ctype and "application/xhtml" not in ctype:
            return None
        return r.text
    except requests.RequestException:
        stats.errors += 1
        return None
    finally:
        if cfg.delay_s > 0:
            time.sleep(cfg.delay_s)


def fetch_raw(
    url: str,
    cfg: CrawlConfig,
    robots: RobotsCache,
    stats: FetchStats,
    accept: str,
) -> bytes | None:
    if not robots.allowed(url, cfg.user_agent):
        stats.skipped_robots += 1
        return None
    sess = _session_get()
    try:
        r = sess.get(url, timeout=cfg.timeout_s, headers={"User-Agent": cfg.user_agent, "Accept": accept})
        stats.fetched += 1
        r.raise_for_status()
        return r.content
    except requests.RequestException:
        stats.errors += 1
        return None
    finally:
        if cfg.delay_s > 0:
            time.sleep(cfg.delay_s)


def _json_block_iter(text: str) -> Iterable[Any]:
    """Parse one or more JSON objects from application/ld+json script tags."""
    soup = BeautifulSoup(text, "html.parser")
    for tag in soup.find_all("script", type=lambda x: x and "ld+json" in x):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            yield json.loads(raw)
        except json.JSONDecodeError:
            continue


def _walk_graph(obj: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        if "@graph" in obj:
            for item in obj["@graph"]:
                _walk_graph(item, out)
        t = obj.get("@type")
        types = t if isinstance(t, list) else ([t] if t else [])
        if any(x in ("Event", "SportsEvent", "BusinessEvent") for x in types if x):
            out.append(obj)
        if any(x == "ItemList" for x in types if x):
            for it in obj.get("itemListElement") or []:
                if not isinstance(it, dict):
                    continue
                if "item" in it:
                    _walk_graph(it["item"], out)
                else:
                    _walk_graph(it, out)
    elif isinstance(obj, list):
        for it in obj:
            _walk_graph(it, out)


def extract_itemlist_urls(html: str, base_url: str, url_filter: str | None) -> list[str]:
    """URLs from JSON-LD ItemList (ListItem.url), joined to the seed site."""
    found: list[str] = []
    for block in _json_block_iter(html):
        stack: list[Any] = [block]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                t = cur.get("@type")
                types = t if isinstance(t, list) else ([t] if t else [])
                if any(x == "ItemList" for x in types if x):
                    for it in cur.get("itemListElement") or []:
                        if not isinstance(it, dict):
                            continue
                        u = it.get("url")
                        if isinstance(u, str):
                            full = urllib.parse.urljoin(base_url, u).split("#", 1)[0]
                            if url_filter and url_filter.lower() not in full.lower():
                                continue
                            if same_site(base_url, full):
                                found.append(full)
                        it_item = it.get("item")
                        if isinstance(it_item, str) and it_item.startswith(("http://", "https://")):
                            full = it_item.split("#", 1)[0]
                            if url_filter and url_filter.lower() not in full.lower():
                                continue
                            if same_site(base_url, full):
                                found.append(full)
                for v in cur.values():
                    stack.append(v)
            elif isinstance(cur, list):
                stack.extend(cur)
    return list(dict.fromkeys(found))


def _addr_to_text(addr: Any) -> str | None:
    if addr is None:
        return None
    if isinstance(addr, str):
        return addr
    if isinstance(addr, dict):
        parts = [
            addr.get("streetAddress"),
            addr.get("addressLocality"),
            addr.get("addressRegion"),
            addr.get("postalCode"),
            addr.get("addressCountry"),
        ]
        s = ", ".join(p for p in parts if p)
        return s or None
    return None


def _uk_hint(text: str | None) -> bool:
    if not text:
        return False
    t = text.lower()
    return "united kingdom" in t or " uk" in t or t.endswith(" uk") or "england" in t or "scotland" in t or "wales" in t or "northern ireland" in t or re.search(r"\b[mn]\d{1,2} \d[a-z]{2}\b", t) is not None


def normalize_event(obj: dict[str, Any], page_url: str) -> dict[str, Any]:
    loc = obj.get("location")
    place_name = None
    addr_text = None
    if isinstance(loc, dict):
        place_name = loc.get("name")
        addr_text = _addr_to_text(loc.get("address"))
    elif isinstance(loc, str):
        place_name = loc

    start = obj.get("startDate") or obj.get("startTime")
    end = obj.get("endDate") or obj.get("endTime")
    name = obj.get("name")
    desc = obj.get("description")
    event_url = obj.get("url")
    if isinstance(event_url, list):
        event_url = next((u for u in event_url if isinstance(u, str)), None)

    row = {
        "title": name if isinstance(name, str) else None,
        "description": desc if isinstance(desc, str) else None,
        "start": start if isinstance(start, str) else None,
        "end": end if isinstance(end, str) else None,
        "place_name": place_name if isinstance(place_name, str) else None,
        "address_text": addr_text,
        "event_url": event_url if isinstance(event_url, str) else None,
        "source_page_url": page_url,
        "sport": obj.get("sport"),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source_kind": "html_ld+json",
    }
    return row


def extract_events_from_html(html: str, page_url: str, uk_only: bool) -> list[dict[str, Any]]:
    graphs: list[dict[str, Any]] = []
    for block in _json_block_iter(html):
        _walk_graph(block, graphs)

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for g in graphs:
        row = normalize_event(g, page_url)
        if uk_only:
            blob = " ".join(
                filter(
                    None,
                    [
                        row.get("address_text"),
                        row.get("place_name"),
                        row.get("description"),
                        row.get("title"),
                    ],
                )
            )
            if not _uk_hint(blob):
                continue
        key = (row.get("title"), row.get("start"), row.get("event_url") or row.get("source_page_url"))
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def _ical_dt_prop_to_iso(component: Any, prop: str) -> str | None:
    raw = component.get(prop)
    if raw is None:
        return None
    try:
        dt = raw.dt  # type: ignore[attr-defined]
    except AttributeError:
        return None
    from datetime import date as date_type

    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    if isinstance(dt, date_type):
        return dt.isoformat()
    return str(dt)


def _ical_text_prop(component: Any, name: str) -> str | None:
    v = component.get(name)
    if v is None:
        return None
    s = str(v)
    return s if s else None


def parse_ics_bytes(data: bytes, source_ics_url: str, uk_only: bool) -> list[dict[str, Any]]:
    if Calendar is None:
        raise RuntimeError("Install icalendar: pip install icalendar")
    cal = Calendar.from_ical(data)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        title = _ical_text_prop(component, "SUMMARY")
        desc = _ical_text_prop(component, "DESCRIPTION")
        loc = _ical_text_prop(component, "LOCATION")
        start = _ical_dt_prop_to_iso(component, "DTSTART")
        end = _ical_dt_prop_to_iso(component, "DTEND")
        event_url = _ical_text_prop(component, "URL")
        row = {
            "title": title,
            "description": desc,
            "start": start,
            "end": end,
            "place_name": None,
            "address_text": loc,
            "event_url": event_url,
            "source_page_url": source_ics_url,
            "sport": None,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "source_kind": "ics",
        }
        if uk_only:
            blob = " ".join(filter(None, [loc, desc, title]))
            if not _uk_hint(blob):
                continue
        key = (title, start, event_url or source_ics_url)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def fetch_parse_ics(
    url: str,
    cfg: CrawlConfig,
    robots: RobotsCache,
    stats: FetchStats,
    uk_only: bool,
) -> list[dict[str, Any]]:
    buf = fetch_raw(
        url,
        cfg,
        robots,
        stats,
        accept="text/calendar,text/plain,application/ics,*/*",
    )
    if not buf:
        return []
    return parse_ics_bytes(buf, url, uk_only)


def row_content_key(row: dict[str, Any]) -> str:
    parts = (
        row.get("source_kind") or "",
        (row.get("title") or "").strip(),
        (row.get("start") or "").strip(),
        (row.get("end") or "").strip(),
        (row.get("event_url") or "").strip(),
        (row.get("source_page_url") or "").strip(),
        (row.get("address_text") or "").strip(),
    )
    h = hashlib.sha256("\0".join(parts).encode("utf-8"))
    return h.hexdigest()


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for r in rows:
        merged[row_content_key(r)] = r
    return list(merged.values())


def sport_to_sql(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(v)


def merge_stats(a: FetchStats, b: FetchStats) -> FetchStats:
    return FetchStats(
        fetched=a.fetched + b.fetched,
        skipped_robots=a.skipped_robots + b.skipped_robots,
        errors=a.errors + b.errors,
    )


def collect_ics_urls(urls: list[str], cfg: CrawlConfig) -> tuple[list[dict[str, Any]], FetchStats]:
    robots = RobotsCache()
    stats = FetchStats()
    rows: list[dict[str, Any]] = []
    for u in urls:
        rows.extend(fetch_parse_ics(u, cfg, robots, stats, cfg.uk_only))
    return rows, stats


def write_sqlite(db_path: str, rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Returns (upserts attempted, total rows in table after)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS race_events (
              content_key TEXT PRIMARY KEY,
              source_kind TEXT NOT NULL,
              title TEXT,
              description TEXT,
              start TEXT,
              end TEXT,
              place_name TEXT,
              address_text TEXT,
              event_url TEXT,
              source_page_url TEXT NOT NULL,
              sport TEXT,
              scraped_at TEXT NOT NULL
            )
            """
        )
        cur = conn.cursor()
        for row in rows:
            ck = row_content_key(row)
            cur.execute(
                """
                INSERT INTO race_events (
                  content_key, source_kind, title, description, start, end,
                  place_name, address_text, event_url, source_page_url, sport, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(content_key) DO UPDATE SET
                  source_kind = excluded.source_kind,
                  title = excluded.title,
                  description = excluded.description,
                  start = excluded.start,
                  end = excluded.end,
                  place_name = excluded.place_name,
                  address_text = excluded.address_text,
                  event_url = excluded.event_url,
                  source_page_url = excluded.source_page_url,
                  sport = excluded.sport,
                  scraped_at = excluded.scraped_at
                """,
                (
                    ck,
                    row.get("source_kind") or "unknown",
                    row.get("title"),
                    row.get("description"),
                    row.get("start"),
                    row.get("end"),
                    row.get("place_name"),
                    row.get("address_text"),
                    row.get("event_url"),
                    row.get("source_page_url") or "",
                    sport_to_sql(row.get("sport")),
                    row.get("scraped_at") or "",
                ),
            )
        conn.commit()
        (total,) = conn.execute("SELECT COUNT(*) FROM race_events").fetchone()
        return len(rows), int(total)
    finally:
        conn.close()


def same_site(seed: str, link: str) -> bool:
    a, b = urllib.parse.urlsplit(seed), urllib.parse.urlsplit(urllib.parse.urljoin(seed, link))
    return a.netloc == b.netloc


def discover_links(html: str, base_url: str, url_filter: str | None) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        full = urllib.parse.urljoin(base_url, href)
        if not same_site(base_url, full):
            continue
        if url_filter and url_filter.lower() not in full.lower():
            continue
        out.append(full.split("#", 1)[0])
    return list(dict.fromkeys(out))


def parse_sitemap(xml_bytes: bytes) -> list[str]:
    root = ElementTree.fromstring(xml_bytes)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls: list[str] = []
    if root.tag.endswith("sitemapindex"):
        for loc in root.findall(".//sm:sitemap/sm:loc", ns):
            if loc.text:
                urls.append(loc.text.strip())
    else:
        for loc in root.findall(".//sm:url/sm:loc", ns):
            if loc.text:
                urls.append(loc.text.strip())
    if not urls and root.tag.endswith("urlset"):
        for loc in root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
            if loc.text:
                urls.append(loc.text.strip())
    return urls


def crawl(
    seeds: list[str],
    cfg: CrawlConfig,
) -> tuple[list[dict[str, Any]], FetchStats]:
    robots = RobotsCache()
    stats = FetchStats()
    results: list[dict[str, Any]] = []
    visited: set[str] = set()
    q: deque[str] = deque()
    for s in seeds:
        q.append(s)

    while q and len(visited) < cfg.max_pages:
        url = q.popleft()
        if url in visited:
            continue
        visited.add(url)
        html = fetch_html(url, cfg, robots, stats)
        if not html:
            continue
        results.extend(extract_events_from_html(html, url, cfg.uk_only))
        if cfg.follow_links:
            batch = discover_links(html, url, cfg.url_filter)
            batch.extend(extract_itemlist_urls(html, url, cfg.url_filter))
            for link in batch:
                if link not in visited and len(visited) + len(q) < cfg.max_pages:
                    q.append(link)

    return results, stats


def crawl_sitemap(
    sitemap_url: str,
    cfg: CrawlConfig,
) -> tuple[list[dict[str, Any]], FetchStats]:
    robots = RobotsCache()
    stats = FetchStats()
    buf = fetch_raw(
        sitemap_url,
        cfg,
        robots,
        stats,
        accept="application/xml,text/xml,*/*",
    )
    if not buf:
        return [], stats
    nested = parse_sitemap(buf)
    to_fetch: list[str] = []
    if nested and any(ns.endswith(".xml") for ns in nested[:3]):
        for su in nested[:200]:
            b = fetch_raw(su, cfg, robots, stats, accept="application/xml,text/xml,*/*")
            if b:
                to_fetch.extend(parse_sitemap(b))
    else:
        to_fetch = nested

    if cfg.url_filter:
        filt = cfg.url_filter.lower()
        to_fetch = [u for u in to_fetch if filt in u.lower()]

    results: list[dict[str, Any]] = []
    for url in to_fetch[: cfg.max_pages]:
        html = fetch_html(url, cfg, robots, stats)
        if html:
            results.extend(extract_events_from_html(html, url, cfg.uk_only))
    return results, stats


def load_seeds(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Collect UK running race rows from event websites.")
    p.add_argument("--url", action="append", dest="urls", help="Seed URL (repeatable).")
    p.add_argument("--seed-urls", help="Text file: one URL per line.")
    p.add_argument("--out", "-o", default="-", help="Output JSONL path (default: stdout).")
    p.add_argument("--delay", type=float, default=1.0, help="Seconds between HTTP requests.")
    p.add_argument("--max-pages", type=int, default=50, help="Max HTML pages to fetch.")
    p.add_argument("--follow-links", action="store_true", help="Queue same-site links from each page.")
    p.add_argument("--url-filter", help="Substring filter for followed links / sitemap URLs (case-insensitive).")
    p.add_argument("--sitemap", help="Sitemap URL to expand then crawl each URL (use with --url-filter).")
    p.add_argument("--uk-only", action="store_true", help="Keep rows that look UK-located (heuristic).")
    p.add_argument("--user-agent", help="Override User-Agent.")
    p.add_argument("--ics", action="append", default=None, metavar="URL", help="ICS calendar URL (repeatable).")
    p.add_argument("--sqlite", metavar="PATH", help="SQLite DB path; table race_events with upsert by content_key.")
    args = p.parse_args(argv)

    cfg = CrawlConfig(
        delay_s=max(0.0, args.delay),
        max_pages=max(1, args.max_pages),
        follow_links=args.follow_links,
        url_filter=args.url_filter,
        uk_only=args.uk_only,
    )
    if args.user_agent:
        cfg.user_agent = args.user_agent

    seeds: list[str] = []
    if args.urls:
        seeds.extend(args.urls)
    if args.seed_urls:
        seeds.extend(load_seeds(args.seed_urls))

    ics_urls = list(args.ics) if args.ics else []
    if not seeds and not args.sitemap and not ics_urls:
        p.error("Provide --url / --seed-urls, --sitemap, and/or --ics.")

    rows: list[dict[str, Any]] = []
    stats = FetchStats()
    if args.sitemap:
        r, st = crawl_sitemap(args.sitemap, cfg)
        rows.extend(r)
        stats = merge_stats(stats, st)
    if seeds:
        r, st = crawl(seeds, cfg)
        rows.extend(r)
        stats = merge_stats(stats, st)
    if ics_urls:
        r, st = collect_ics_urls(ics_urls, cfg)
        rows.extend(r)
        stats = merge_stats(stats, st)

    rows = dedupe_rows(rows)

    out_f = open(args.out, "w", encoding="utf-8") if args.out != "-" else sys.stdout
    try:
        for row in rows:
            out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
    finally:
        if out_f is not sys.stdout:
            out_f.close()

    sqlite_upserts = 0
    sqlite_total: int | None = None
    if args.sqlite:
        sqlite_upserts, sqlite_total = write_sqlite(args.sqlite, rows)

    summary = {
        "events_written": len(rows),
        "http_fetches": stats.fetched,
        "skipped_robots": stats.skipped_robots,
        "errors": stats.errors,
    }
    if args.sqlite:
        summary["sqlite_upserts"] = sqlite_upserts
        summary["sqlite_total_rows"] = sqlite_total
    print(json.dumps(summary, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
