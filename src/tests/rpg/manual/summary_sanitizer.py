"""Summary sanitizer loader.

The manual summary sanitizer implementation is stored in ordered fragments under
``summary_sanitizer_parts`` so the active Python file stays below the RPG
line-count limit while preserving the historical module API.
"""

from __future__ import annotations

import linecache
from pathlib import Path
from typing import List

_RUNTIME_LOADED = False


def _summary_sanitizer_fragment_paths() -> List[Path]:
    parts_dir = Path(__file__).with_name("summary_sanitizer_parts")
    fragments = sorted(parts_dir.glob("*.pyfrag"))
    if not fragments:
        raise RuntimeError(f"No summary sanitizer source fragments found in {parts_dir}")
    return fragments


def _combine_summary_sanitizer_fragments(fragments: List[Path]) -> str:
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


def _load_summary_sanitizer_runtime() -> None:
    global _RUNTIME_LOADED
    if _RUNTIME_LOADED:
        return
    fragments = _summary_sanitizer_fragment_paths()
    combined_source = _combine_summary_sanitizer_fragments(fragments)
    combined_filename = str(Path(__file__).with_name("summary_sanitizer_parts") / "__combined_summary_sanitizer__.py")
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


_load_summary_sanitizer_runtime()
