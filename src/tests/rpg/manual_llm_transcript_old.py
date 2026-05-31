"""Compatibility shim for the archived manual RPG LLM transcript runner."""

from __future__ import annotations

import runpy
from pathlib import Path


ARCHIVED_MANUAL_LLM_TRANSCRIPT = (
    Path(__file__).resolve().parents[1] / "rpg_legacy" / "manual_llm_transcript_old.py"
)


def main() -> None:
    runpy.run_path(str(ARCHIVED_MANUAL_LLM_TRANSCRIPT), run_name="__main__")


if __name__ == "__main__":
    main()
