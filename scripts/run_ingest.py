#!/usr/bin/env python3
"""Run ``python scripts/run_ingest.py --help`` from the repo root (after ``pip install -e packages/fmr_core``).

Subcommands live in ``scripts/ingest/``. Use ``ingest-sample --source curated`` with a JSON seed
(see ``data/ingest_seeds/curated_races.sample.json``) to turn pasted rows into ``Race`` JSON.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
_FM_CORE_SRC = _ROOT / "packages" / "fmr_core" / "src"
for p in (_SCRIPTS, _FM_CORE_SRC):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from ingest.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
