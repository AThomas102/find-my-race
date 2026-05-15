# Scripts

Respect **robots.txt**, site **terms of use**, and **privacy** when crawling or storing data.

| Script | Role |
|--------|------|
| `uk_running_events_crawl.py` | Discover race rows (JSON-LD / ICS) → JSONL or SQLite `race_events`. |
| `powerof10_athlete_scraper.py` | Fetch Po10 athlete pages by UUID for performances (no bulk search API). |
| `compute_field_summary.py` | Turn a list of equivalent 5K seconds into `median` / quartiles → merge into `Race.field_summary` in your pipeline. |

The website reads normalized races from `data/demo_races.json` (or `FMR_RACES_JSON`). In production, agents should ingest into a database and expose the same **`Race`** JSON shape consumed by `fmr_core.models.Race`.
