"""Autoplay campaign harness loader.

N117.5 replaces the anonymous N117.4 ``chunk_###.pyfrag`` files with named,
ordered source fragments under ``autoplay_llm_campaign_parts``. The fragments
are still executed as one combined source unit so the historical
``python src/tests/rpg/autoplay_llm_campaign.py`` entrypoint and runtime
semantics stay stable while future patches can target small logical files.
"""

from __future__ import annotations

import linecache
from pathlib import Path
from typing import Dict, List

_RUNTIME_LOADED = False


def _autoplay_campaign_fragment_paths() -> List[Path]:
    parts_dir = Path(__file__).with_name("autoplay_llm_campaign_parts")
    fragments = sorted(
        path
        for path in parts_dir.glob("*.pyfrag")
        if not path.name.startswith("chunk_")
    )
    if not fragments:
        raise RuntimeError(f"No autoplay campaign source fragments found in {parts_dir}")
    return fragments


def _load_autoplay_campaign_runtime() -> None:
    global _RUNTIME_LOADED
    if _RUNTIME_LOADED:
        return
    fragments = _autoplay_campaign_fragment_paths()
    combined_source = "\n".join(fragment.read_text(encoding="utf-8") for fragment in fragments)
    combined_filename = str(
        Path(__file__).with_name("autoplay_llm_campaign_parts")
        / "__combined_autoplay_llm_campaign__.py"
    )
    # Keep inspect.getsource()/getsourcelines() working for functions defined
    # inside the synthetic combined source. Several autoplay self-checks inspect
    # their own runtime functions; without a linecache entry, inspect can raise
    # "lineno is out of bounds" because the compiled filename is virtual.
    linecache.cache[combined_filename] = (
        len(combined_source),
        None,
        combined_source.splitlines(keepends=True),
        combined_filename,
    )
    chunk_globals: Dict[str, object] = globals()
    _RUNTIME_LOADED = True
    exec(
        compile(
            combined_source,
            combined_filename,
            "exec",
        ),
        chunk_globals,
        chunk_globals,
    )


_load_autoplay_campaign_runtime()
