"""Autoplay campaign harness loader.

N117.4 mechanically split the historical 27k+ line implementation into bounded
source fragments under ``autoplay_llm_campaign_parts``. This wrapper preserves
``python src/tests/rpg/autoplay_llm_campaign.py`` and import-time behavior while
making future edits small enough for GitHub App file operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

_RUNTIME_LOADED = False


def _autoplay_campaign_chunk_paths() -> List[Path]:
    parts_dir = Path(__file__).with_name("autoplay_llm_campaign_parts")
    chunks = sorted(parts_dir.glob("chunk_*.pyfrag"))
    if not chunks:
        raise RuntimeError(f"No autoplay campaign source chunks found in {parts_dir}")
    return chunks


def _load_autoplay_campaign_runtime() -> None:
    global _RUNTIME_LOADED
    if _RUNTIME_LOADED:
        return
    chunks = _autoplay_campaign_chunk_paths()
    combined_source = "\n".join(chunk.read_text(encoding="utf-8") for chunk in chunks)
    chunk_globals: Dict[str, object] = globals()
    _RUNTIME_LOADED = True
    exec(
        compile(
            combined_source,
            str(Path(__file__).with_name("autoplay_llm_campaign_parts") / "__combined_autoplay_llm_campaign__.py"),
            "exec",
        ),
        chunk_globals,
        chunk_globals,
    )


_load_autoplay_campaign_runtime()
