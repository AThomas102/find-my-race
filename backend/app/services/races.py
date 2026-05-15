from __future__ import annotations

import json
from pathlib import Path

from fmr_core.models import Race


def load_races(path: Path) -> list[Race]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected JSON array in {path}")
    return [Race.model_validate(x) for x in raw]
