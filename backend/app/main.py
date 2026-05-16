from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import health, search

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def races_source_from_env() -> Path:
    """
    Resolved catalog root:
      - ``FMR_RACES_JSON``: explicit file OR directory (single-file load if file; merged catalog if dir).
      - else ``FMR_DATA_DIR``: directory merged from ``demo_races.json`` + ``races/*.json``.
      - else `<repo>/data`` (merged catalog).
    """
    if override := os.environ.get("FMR_RACES_JSON"):
        return Path(override).expanduser()
    if dh := os.environ.get("FMR_DATA_DIR"):
        return Path(dh).expanduser()
    return _DEFAULT_DATA_DIR


RACES_SOURCE = races_source_from_env()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Find My Race API",
        version="0.1.0",
        description="Search races with geographic and field-aware matching. See AGENTS.md in repo root.",
    )
    origins = os.environ.get("FMR_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.races_source = RACES_SOURCE  # Path to data directory or explicit JSON file
    app.include_router(health.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    return app


app = create_app()
