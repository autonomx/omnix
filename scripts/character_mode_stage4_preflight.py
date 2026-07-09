#!/usr/bin/env python3
"""CLI entry point for the Character Mode Stage 4 shared-memory pilot."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.characters.stage4_preflight import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
