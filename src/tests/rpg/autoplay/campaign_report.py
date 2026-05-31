"""Campaign report loader.

The rich autoplay campaign report is stored as ordered source fragments under
``campaign_report_parts``.  Loading them as one synthetic module preserves the
historical public/private helper API while keeping active Python files small.
"""

from __future__ import annotations

import linecache
import sys
from pathlib import Path
from typing import List

_RUNTIME_LOADED = False
_RUNTIME_MODULE_ALIASES = (
    "tests.rpg.autoplay.campaign_report",
    "rpg.autoplay.campaign_report",
)


def _register_campaign_report_aliases() -> None:
    module = sys.modules.get(__name__)
    if module is None:
        return
    for name in _RUNTIME_MODULE_ALIASES:
        sys.modules[name] = module


def _campaign_report_fragment_paths() -> List[Path]:
    parts_dir = Path(__file__).with_name("campaign_report_parts")
    fragments = sorted(parts_dir.glob("*.pyfrag"))
    if not fragments:
        raise RuntimeError(f"No campaign report source fragments found in {parts_dir}")
    return fragments


def _combine_campaign_report_fragments(fragments: List[Path]) -> str:
    future_imports: List[str] = []
    seen_futures = set()
    body_parts: List[str] = []
    for fragment in fragments:
        body_lines: List[str] = []
        for line in fragment.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("from __future__ import "):
                if stripped not in seen_futures:
                    seen_futures.add(stripped)
                    future_imports.append(stripped)
                continue
            body_lines.append(line)
        body_parts.append("\n".join(body_lines))
    prefix = "\n".join(future_imports)
    body = "\n".join(body_parts)
    return prefix + "\n\n" + body if prefix else body


def _load_campaign_report_runtime() -> None:
    global _RUNTIME_LOADED
    if _RUNTIME_LOADED:
        return
    _register_campaign_report_aliases()
    fragments = _campaign_report_fragment_paths()
    combined_source = _combine_campaign_report_fragments(fragments)
    combined_filename = str(Path(__file__).with_name("campaign_report_parts") / "__combined_campaign_report__.py")
    linecache.cache[combined_filename] = (
        len(combined_source),
        None,
        combined_source.splitlines(keepends=True),
        combined_filename,
    )
    chunk_globals = globals()
    chunk_globals.setdefault("__file__", str(Path(__file__).resolve()))
    _RUNTIME_LOADED = True
    exec(compile(combined_source, combined_filename, "exec"), chunk_globals, chunk_globals)
    _register_campaign_report_aliases()


_load_campaign_report_runtime()
