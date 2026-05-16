# Agent onboarding: Find My Race

This repository is designed so humans and **automation agents** can extend it safely. Read this file before making product or architecture changes.

## Product intent

- **Primary goal**: Help runners **discover races** with **geographic** filtering and **field-aware** matching (how the user’s ability compares to typical finishers or entrants).
- **Secondary / future**: Course attributes (flat vs hilly, surface, elevation profile), registration status, price bands, accessibility, etc. The data model reserves extensibility via `course` and `metadata` objects—prefer adding fields there over one-off API flags.

## Architecture (modular)

| Layer | Path | Responsibility |
|--------|------|----------------|
| Domain + algorithms | `packages/fmr_core/` | Race/field models, equivalent-time / handicap math, pure search scoring (no I/O). **Safe for unit tests.** |
| Ingestion | `scripts/` | Crawlers (`uk_running_events_crawl.py`), modular merge CLI (`scripts/run_ingest.py` → `scripts/ingest/`), Po10 athlete fetch (`powerof10_athlete_scraper.py`), field-stat helpers. Respect robots.txt / site terms. |
| HTTP API | `backend/app/` | FastAPI: validates requests, loads data, calls `fmr_core.search`. Agents add endpoints by **thin** wrappers over core logic. |
| UI | `web/` | React (Vite + TypeScript). Calls `/api/*` only; no duplicate business rules in the browser except display formatting. |

**Rule**: Put business logic in `fmr_core`. The API layer should orchestrate only (load JSON/SQL later, auth, pagination).

## Data flow for handicap / field strength

1. **Races** are storedwith optional `field_summary` (median/p bands of equivalent 5K time, sample size, provenance).
2. **User** submits a recent performance (distance + duration). Core converts to **equivalent 5K seconds** (Riegel-style), then compares to each race’s `field_summary`.
3. **Population of `field_summary`** (agent tasks):
  - **Past results**: Parse official results → map names to Po10 athlete IDs where possible → derive equivalent 5K times → feed `scripts/compute_field_summary.py` and merge JSON into each `Race.field_summary`.
   - **Current entrants**: Same idea when start lists exist; weaker provenance until race day.

Po10 unattended search often hits CAPTCHA; the scraper is aimed at **known athlete UUIDs** or exported HTML—not bulk discovery via search APIs.

## File contracts

- `data/demo_races.json`: Small **hand-curated or ingest-merged** catalog for local dev (real events / public URLs only; no synthetic generators). Schema matches `fmr_core.models.Race`. Larger merged catalogs live under `data/races/*.json` when you run `python scripts/run_ingest.py ingest-sample --source curated --config <seed.json> --out data/races/<name>.json --merge`.
- Future: replace loader in `backend/app/services/races.py` with SQLite/Postgres while keeping the same **core** search inputs/outputs.

## How to extend without breaking scales

1. **New filter** (e.g. “trail only”): Add optional field under `Race.course` or `Race.metadata`, implement filter in `fmr_core/search.py`, plumb query param in API + UI.
2. **New scoring dimension**: Extend `RaceMatch.reasons` and `composite_score` calculation in core; keep API response backward compatible (`Optional` fields).
3. **New data source**: Add a script under `scripts/` that outputs rows aligned with ingest schema; prefer normalizing into `Race` JSON or DB rows.

## Commands (local)

- Backend: `cd backend && pip install -r requirements.txt && pip install -e ../packages/fmr_core && uvicorn app.main:app --reload`
- Frontend: `cd web && npm install && npm run dev`
- Core tests: `cd packages/fmr_core && pip install -e ".[dev]" && pytest`
- Curated ingest (local JSON → `Race` file): `python scripts/run_ingest.py ingest-sample --source curated --config data/ingest_seeds/curated_races.sample.json --out data/races/import_demo.json --merge`
- Listing preview only: `python scripts/run_ingest.py list --source curated --config data/ingest_seeds/curated_races.sample.json`


