from __future__ import annotations

import json
from pathlib import Path

from fmr_core.models import Race


def load_races(path: Path) -> list[Race]:
    """Load a single JSON array file."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected JSON array in {path}")
    return [Race.model_validate(x) for x in raw]


def load_race_catalog_dir(data_dir: Path) -> list[Race]:
    """
    Merge `demo_races.json` with `races/*.json` (later files alphabetically override earlier ids).

    Use this layout to grow calendar data incrementally during ingestion pipelines.
    """
    merged: dict[str, Race] = {}
    files: list[Path] = []
    demo = data_dir / "demo_races.json"
    if demo.exists():
        files.append(demo)
    extra = data_dir / "races"
    if extra.is_dir():
        files.extend(sorted(extra.glob("*.json")))
    for fp in files:
        for race in load_races(fp):
            merged[race.id] = race
    return list(merged.values())


def load_races_from_source(src: Path) -> list[Race]:
    """If ``src`` is a directory load merged catalog; if a file load that file."""
    return load_race_catalog_dir(src) if src.is_dir() else load_races(src)
