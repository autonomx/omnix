from __future__ import annotations

import builtins
import json
import re
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SOURCE = "autoplay_turn_error_diagnostics_hook_v4"
SUMMARY_NAME = "autoplay-turn-error-diagnostics.json"
FORMAT_EXC_NAME = "autoplay-exception-tracebacks.json"
_DEFAULT_AUTOPLAY_RESULT_DIR_PARTS = (
    "resources",
    "data",
    "test-results",
    "autoplay-100-n82-travel-location-progression",
)
_EVENT_WORD = "ERR" + "OR"
_PATTERN = re.compile(r"TURN\s+(?P<turn>\d+)\s+" + _EVENT_WORD + r":\s+(?P<etype>[A-Za-z_][A-Za-z0-9_]*):\s*(?P<message>.*)")
_INSTALLED = False
_OUTPUT_DIR: Optional[Path] = None
_ORIGINAL_PRINT = builtins.print
_ORIGINAL_FORMAT_EXC = traceback.format_exc
_ORIGINAL_FORMAT_EXCEPTION = traceback.format_exception
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


def _default_output_dir() -> Path:
    return Path.cwd().joinpath(*_DEFAULT_AUTOPLAY_RESULT_DIR_PARTS)


def _resolved_output_dir() -> Path:
    return _OUTPUT_DIR or _default_output_dir()


def _summary_path() -> Path:
    return _resolved_output_dir() / SUMMARY_NAME


def _format_exc_path() -> Path:
    return _resolved_output_dir() / FORMAT_EXC_NAME


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


def _turn_index_from_tb(tb: Any) -> int | None:
    cursor = tb
    while cursor is not None:
        try:
            frame = cursor.tb_frame
            for key in ("turn_index", "turn", "turn_number", "tick"):
                raw = frame.f_locals.get(key)
                if raw is not None:
                    return int(raw)
        except Exception:
            pass
        cursor = getattr(cursor, "tb_next", None)
    return None


def _active_exception_payload() -> Dict[str, Any]:
    exc_type, exc, tb = sys.exc_info()
    if exc_type is None or exc is None or tb is None:
        return {"ok": False, "reason": "no_active_exception"}
    try:
        extracted = traceback.extract_tb(tb, limit=_MAX_TRACEBACK_FRAMES)
        formatted = _ORIGINAL_FORMAT_EXCEPTION(exc_type, exc, tb, limit=_MAX_TRACEBACK_FRAMES)
        return {
            "ok": True,
            "error_type": getattr(exc_type, "__name__", str(exc_type)),
            "message": str(exc)[-1000:],
            "turn_index": _turn_index_from_tb(tb),
            "traceback_frames": [_safe_frame(frame) for frame in extracted],
            "traceback_frame_count": len(extracted),
            "repeated_frames": _summarize_repeated_frames(list(extracted)),
            "formatted_traceback_tail": formatted[-_MAX_FORMATTED_TRACEBACK_LINES:],
        }
    except Exception as capture_error:
        return {"ok": False, "reason": "traceback_capture_failed", "error": repr(capture_error)}


def _append_json_event(path: Path, event: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_payload(path)
    events = list(payload.get("events") or [])
    events.append(event)
    payload.update(
        {
            "ok": True,
            "source": SOURCE,
            "event_count": len(events),
            "events": events[-_MAX_EVENTS:],
        }
    )
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _record_format_exc_event(formatted_text: str) -> None:
    active_exception = _active_exception_payload()
    _append_json_event(
        _format_exc_path(),
        {
            "event_class": "traceback_format_exc",
            "active_exception": active_exception,
            "active_exception_available": bool(active_exception.get("ok")),
            "turn_index": active_exception.get("turn_index"),
            "formatted_text_tail": formatted_text[-8000:],
            "source": SOURCE,
        },
    )


def guarded_format_exc(*args: Any, **kwargs: Any) -> str:
    text = _ORIGINAL_FORMAT_EXC(*args, **kwargs)
    try:
        _record_format_exc_event(text)
    except Exception:
        pass
    return text


def _record_line(line: str) -> None:
    match = _PATTERN.search(line)
    if not match:
        return
    active_exception = _active_exception_payload()
    _append_json_event(
        _summary_path(),
        {
            "turn_index": int(match.group("turn")),
            "error_type": match.group("etype"),
            "message": match.group("message"),
            "line": line[-2000:],
            "active_exception": active_exception,
            "active_exception_available": bool(active_exception.get("ok")),
            "stack_tail": traceback.format_stack(limit=30),
            "source": SOURCE,
        },
    )


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
    traceback.format_exc = guarded_format_exc  # type: ignore[assignment]
    _INSTALLED = True
    return True


def install_turn_error_diagnostics_hook_from_argv(argv: Iterable[str]) -> bool:
    return install_turn_error_diagnostics_hook(output_dir=_parse_output_dir(argv))
