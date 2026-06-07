"""Autoplay-only deepcopy recursion guard.

Long 100-turn runs can accumulate deeply nested or cyclic diagnostic state.  The
runtime imports ``deepcopy`` from ``copy`` in several generated fragments, so the
loader installs this guard before fragment execution.  The guard keeps normal
``deepcopy`` behavior for healthy values and falls back to a bounded structural
clone only when ``RecursionError`` is raised.
"""
from __future__ import annotations

import copy
import json
import traceback
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

SOURCE = "autoplay_deepcopy_recursion_guard_v1"
SUMMARY_NAME = "autoplay-deepcopy-recursion-guard-summary.json"
_INSTALLED = False
_ORIGINAL_DEEPCOPY = copy.deepcopy
_OUTPUT_DIR: Optional[Path] = None
_MAX_DEPTH = 80
_MAX_ITEMS = 200


def _parse_output_dir(argv: Iterable[str]) -> Optional[Path]:
    args = list(argv)
    for index, value in enumerate(args):
        if value == "--output-dir" and index + 1 < len(args):
            return Path(args[index + 1])
        if value.startswith("--output-dir="):
            return Path(value.split("=", 1)[1])
    return None


def _summary_path() -> Optional[Path]:
    return (_OUTPUT_DIR / SUMMARY_NAME) if _OUTPUT_DIR is not None else None


def _safe_clone(value: Any, *, depth: int = 0, seen: Optional[set[int]] = None) -> Any:
    if seen is None:
        seen = set()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if depth >= _MAX_DEPTH:
        return {"__truncated__": True, "reason": "max_depth", "source": SOURCE}
    object_id = id(value)
    if object_id in seen:
        return {"__cycle__": True, "source": SOURCE}
    seen.add(object_id)
    try:
        if isinstance(value, dict):
            cloned: Dict[str, Any] = {}
            for index, (key, nested) in enumerate(value.items()):
                if index >= _MAX_ITEMS:
                    cloned["__truncated_items__"] = len(value) - _MAX_ITEMS
                    break
                cloned[str(_safe_clone(key, depth=depth + 1, seen=seen))] = _safe_clone(
                    nested,
                    depth=depth + 1,
                    seen=seen,
                )
            return cloned
        if isinstance(value, (list, tuple, set)):
            items = list(value)
            cloned_items = [
                _safe_clone(item, depth=depth + 1, seen=seen)
                for item in items[:_MAX_ITEMS]
            ]
            if len(items) > _MAX_ITEMS:
                cloned_items.append({"__truncated_items__": len(items) - _MAX_ITEMS, "source": SOURCE})
            return cloned_items if not isinstance(value, tuple) else tuple(cloned_items)
        return repr(value)
    finally:
        seen.discard(object_id)


def _record_fallback(exc: BaseException) -> None:
    path = _summary_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any]
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            payload = existing if isinstance(existing, dict) else {}
        except Exception:
            payload = {}
    else:
        payload = {}
    events = list(payload.get("events") or [])
    events.append(
        {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback_tail": traceback.format_exc(limit=20),
            "source": SOURCE,
        }
    )
    payload.update({"ok": True, "source": SOURCE, "fallback_count": len(events), "events": events[-20:]})
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def guarded_deepcopy(value: Any, memo: Any = None) -> Any:
    try:
        if memo is None:
            return _ORIGINAL_DEEPCOPY(value)
        return _ORIGINAL_DEEPCOPY(value, memo)
    except RecursionError as exc:
        _record_fallback(exc)
        return _safe_clone(value)


def install_deepcopy_recursion_guard(*, output_dir: str | Path | None = None) -> bool:
    global _INSTALLED, _OUTPUT_DIR
    if output_dir is not None:
        _OUTPUT_DIR = Path(output_dir)
    if _INSTALLED:
        return False
    copy.deepcopy = guarded_deepcopy  # type: ignore[assignment]
    _INSTALLED = True
    return True


def install_deepcopy_recursion_guard_from_argv(argv: Iterable[str]) -> bool:
    return install_deepcopy_recursion_guard(output_dir=_parse_output_dir(argv))
