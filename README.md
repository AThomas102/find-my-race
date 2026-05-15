# Find My Race

A modular web app to **discover running races** with:

- **Geographic search** (postcode/city text + radius; optional lat/lon when present on events)
- **Smart / field-aware search**: compare **your recent race time** to each event’s summarized field ability (median equivalent 5K and spread), powered by logic in `packages/fmr_core/`
- **Course hints** (demo): terrain tags such as flat / undulating / hilly — easy to extend

## Quick start

1. **Backend** (API + demo data):

   ```bash
   cd backend
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   pip install -e ../packages/fmr_core
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Frontend**:

   ```bash
   cd web
   npm install
   npm run dev
   ```

3. Open the URL printed by Vite (usually `http://localhost:5173`). The UI proxies `/api` to the backend—see `web/vite.config.ts`.

## Scripts (data ingestion)

See `scripts/README.md`. Crawlers live under `scripts/` and feed normalized race rows or athlete JSON used to compute **field summaries**.

## Agents

If you are an AI agent working in this repo, read **[AGENTS.md](./AGENTS.md)** first.

## License

Specify as needed by the repository owner.
