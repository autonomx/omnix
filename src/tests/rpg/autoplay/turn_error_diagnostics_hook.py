"""Per-turn error diagnostics for autoplay runs.

The generated runtime currently emits concise ``TURN N ERROR`` lines for some
caught turn failures.  This hook records those emissions with both the active
exception traceback, when the print happens inside an ``except`` block, and a
bounded Python stack tail from the error-handling site.
"""
from __future__ import annotations

import builtins
import json
import re
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SOURCE = "autoplay_turn_error_diagnostics_hook_v2"
SUMMARY_NAME = "autoplay-turn-error-diagnostics.json"
_PATTERN = re.compile(r"TURN\s+(?P<turn>\d+)\s+ERROR:\s+(?P<etype>[A-Za-z_][A-Za-z0-9_]*):\s*(?P<message>.*)")
_INSTALLED = False
_OUTPUT_DIR: Optional[Path] = None
_ORIGINAL_PRINT = builtins.print
_MAX_EVENTS = 200
_MAX_TRACEBACK_FRAMES = 80
_MAX_FORMATTED_TRACEBACK_LINES = 160


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


def _load_payload(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"ok": True, "source": SOURCE, "events": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"ok": True, "source": SOURCE, "events": []}
    except Exception:
        return {"ok": True, "source": SOURCE, "events": []}


def _safe_frame(frame: traceback.FrameSummary) -> Dict[str, Any]:
    return {
        "filename": str(frame.filename)[-300:],
        "line_number": int(frame.lineno),
        "function_name": str(frame.name)[-200:],
        "line": (str(frame.line or "")[-500:] if frame.line is not None else ""),
    }


def _frame_key(frame: traceback.FrameSummary) -> str:
    return f"{frame.filename}:{frame.lineno}:{frame.name}"


def _summarize_repeated_frames(frames: List[traceback.FrameSummary]) -> List[Dict[str, Any]]:
    counts: Dict[str, Dict[str, Any]] = {}
    for frame in frames:
        key = _frame_key(frame)
        entry = counts.setdefault(
            key,
            {
                "count": 0,
                "filename": str(frame.filename)[-300:],
                "line_number": int(frame.lineno),
                "function_name": str(frame.name)[-200:],
                "line": (str(frame.line or "")[-500:] if frame.line is not None else ""),
            },
        )
        entry["count"] += 1
    repeated = [entry for entry in counts.values() if int(entry.get("count") or 0) > 1]
    repeated.sort(key=lambda value: int(value.get("count") or 0), reverse=True)
    return repeated[:20]


def _active_exception_payload() -> Dict[str, Any]:
    exc_type, exc, tb = sys.exc_info()
    if exc_type is None or exc is None or tb is None:
        return {"ok": False, "reason": "no_active_exception"}
    try:
        extracted = traceback.extract_tb(tb, limit=_MAX_TRACEBACK_FRAMES)
        formatted = traceback.format_exception(exc_type, exc, tb, limit=_MAX_TRACEBACK_FRAMES)
        return {
            "ok": True,
            "error_type": getattr(exc_type, "__name__", str(exc_type)),
            "message": str(exc)[-1000:],
            "traceback_frames": [_safe_frame(frame) for frame in extracted],
            "traceback_frame_count": len(extracted),
            "repeated_frames": _summarize_repeated_frames(list(extracted)),
            "formatted_traceback_tail": formatted[-_MAX_FORMATTED_TRACEBACK_LINES:],
        }
    except Exception as capture_error:
        return {"ok": False, "reason": "traceback_capture_failed", "error": repr(capture_error)}


def _record_line(line: str) -> None:
    match = _PATTERN.search(line)
    if not match:
        return
    path = _summary_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_payload(path)
    events = list(payload.get("events") or [])
    active_exception = _active_exception_payload()
    events.append(
        {
            "turn_index": int(match.group("turn")),
            "error_type": match.group("etype"),
            "message": match.group("message"),
            "line": line[-2000:],
            "active_exception": active_exception,
            "active_exception_available": bool(active_exception.get("ok")),
            "stack_tail": traceback.format_stack(limit=30),
            "source": SOURCE,
        }
    )
    payload.update(
        {
            "ok": True,
            "source": SOURCE,
            "event_count": len(events),
            "events": events[-_MAX_EVENTS:],
        }
    )
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def guarded_print(*args: Any, **kwargs: Any) -> None:
    _ORIGINAL_PRINT(*args, **kwargs)
    try:
        text = " ".join(str(arg) for arg in args)
        _record_line(text)
    except Exception:
        return


def install_turn_error_diagnostics_hook(*, output_dir: str | Path | None = None) -> bool:
    global _INSTALLED, _OUTPUT_DIR
    if output_dir is not None:
        _OUTPUT_DIR = Path(output_dir)
    if _INSTALLED:
        return False
    builtins.print = guarded_print  # type: ignore[assignment]
    _INSTALLED = True
    return True


def install_turn_error_diagnostics_hook_from_argv(argv: Iterable[str]) -> bool:
    return install_turn_error_diagnostics_hook(output_dir=_parse_output_dir(argv))
