"""Autoplay campaign harness loader.

N117.5 replaces the anonymous N117.4 ``chunk_###.pyfrag`` files with named,
ordered source fragments under ``autoplay_llm_campaign_parts``. The fragments
are still executed as one combined source unit so the historical
``python src/tests/rpg/autoplay_llm_campaign.py`` entrypoint and runtime
semantics stay stable while future patches can target small logical files.
"""

from __future__ import annotations

import linecache
import sys
from pathlib import Path
from typing import Dict, List

_RUNTIME_LOADED = False
_RUNTIME_MODULE_ALIASES = (
    "tests.rpg.autoplay_llm_campaign",
    "rpg.autoplay_llm_campaign",
)


def _register_autoplay_runtime_aliases() -> None:
    """Expose this running script under import names used by helper modules.

    Some helper modules import ``tests.rpg.autoplay_llm_campaign`` at runtime to
    access functions defined by the combined fragment source.  When this file is
    executed as a script, those functions live on ``__main__`` after
    ``_load_autoplay_campaign_runtime()``.  Register aliases so those imports
    resolve to the already-loaded runtime module instead of importing a second,
    lightweight loader-only copy.
    """

    module = sys.modules.get(__name__)
    if module is None:
        return
    for name in _RUNTIME_MODULE_ALIASES:
        sys.modules[name] = module


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


def _combine_autoplay_campaign_fragments(fragments: List[Path]) -> str:
    """Combine fragments while keeping all future imports at file start.

    The fragment loader executes every ``*.pyfrag`` as one synthetic module.
    Late fixes may need lexicographically-early fragments to register guards
    before the rest of the runtime loads, but many existing fragments still
    contain ``from __future__`` imports.  Python requires those imports before any
    other executable statement in the *combined* module, so normalize them here.
    """

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
    if prefix:
        return prefix + "\n\n" + body
    return body


def _load_autoplay_campaign_runtime() -> None:
    global _RUNTIME_LOADED
    if _RUNTIME_LOADED:
        return
    _register_autoplay_runtime_aliases()
    fragments = _autoplay_campaign_fragment_paths()
    combined_source = _combine_autoplay_campaign_fragments(fragments)
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
    chunk_globals.setdefault("__file__", str(Path(__file__).resolve()))
    original_name = chunk_globals.get("__name__", __name__)
    # N118.3: fragment 66 historically contains an ``if __name__ == "__main__"``
    # block.  After late fragments were added, that block exited before fragments
    # 67+ loaded, so N117.8/N118/N118.1/N118.2 hooks never ran.  Execute the
    # combined fragment source under an internal name, then call main() once from
    # this wrapper after every fragment has loaded.
    chunk_globals["__name__"] = "_autoplay_campaign_runtime"
    _RUNTIME_LOADED = True
    try:
        exec(
            compile(
                combined_source,
                combined_filename,
                "exec",
            ),
            chunk_globals,
            chunk_globals,
        )
    finally:
        chunk_globals["__name__"] = original_name
        _register_autoplay_runtime_aliases()


if __name__ == "__main__":
    _register_autoplay_runtime_aliases()
    _load_autoplay_campaign_runtime()
    main_fn = globals().get("main")
    if not callable(main_fn):
        raise RuntimeError("autoplay_campaign_main_missing_after_fragment_load")
    raise SystemExit(main_fn(sys.argv[1:]))
