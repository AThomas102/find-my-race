from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import health, search

_DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "demo_races.json"
DATA_PATH = Path(os.environ.get("FMR_RACES_JSON", str(_DEFAULT_DATA)))


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
    app.state.races_path = DATA_PATH
    app.include_router(health.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    return app


app = create_app()
