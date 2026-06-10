"""Runtime apply-chain diagnostic hook for autoplay runs.

The interactive CLI can fail after the manual turn runtime returns a payload but
before the harness materializes the final transcript row.  This hook installs a
very small trace probe around generated runtime functions so the next failing run
persists the exact function, local payload shape, return payload shape, and any
caught exception frames without walking recursive objects unsafely.
"""

from __future__ import annotations

import atexit
import json
import sys
import time
import traceback
import zipfile
from pathlib import Path
from types import FrameType, TracebackType
from typing import Any, Dict, Iterable, List, Mapping, Optional

_SOURCE = "autoplay_runtime_apply_chain_probe_v2"
ARTIFACT_NAME = "autoplay-runtime-apply-chain-probe.json"
_OUTPUT_DIR: Path | None = None
_INSTALLED = False
_PREVIOUS_TRACE = None
_MAX_EVENTS = 500
_MAX_DEPTH = 5
_MAX_ITEMS = 80
_MAX_STRING = 2000
_TARGET_NAME_TOKENS = (
    "apply_turn",
    "call_turn_runtime",
    "run_one_manual_turn",
    "manual_turn",
)
_INTERESTING_LOCAL_NAMES = (
    "turn_index",
    "player_input",
    "player_action",
    "session_id",
    "runtime_narration",
    "runtime_error",
    "turn_result",
    "result",
    "raw_result",
    "resolved_result",
    "extracted",
    "manual_harness_trace",
    "manual_harness_trace_summary",
    "manual_stage_trace",
    "manual_turn_summary",
    "turn_perf_trace",
    "turn_perf_trace_summary",
    "interactive_cli_intent_diagnostics",
    "classification",
    "intent_classification",
)


def _output_dir_from_argv(argv: Iterable[str]) -> Path | None:
    args = list(argv)
    for index, value in enumerate(args):
        if value == "--output-dir" and index + 1 < len(args):
            return Path(args[index + 1])
        if value.startswith("--output-dir="):
            return Path(value.split("=", 1)[1])
    return None


def _default_output_dir() -> Path:
    return Path.cwd() / "resources" / "data" / "test-results" / "autoplay-100-n82-travel-location-progression"


def _diagnostic_output_dir() -> Path:
    return _OUTPUT_DIR or _default_output_dir()


def _artifact_path() -> Path:
    return _diagnostic_output_dir() / ARTIFACT_NAME


def _safe_text(value: object, *, limit: int = _MAX_STRING) -> str:
    try:
        text = "" if value is None else str(value)
    except Exception as exc:  # pragma: no cover - defensive only
        text = f"<{type(exc).__name__}>"
    return text if len(text) <= limit else text[:limit] + "...<truncated>"


def _safe_json(value: Any, *, depth: int = 0, seen: Optional[set[int]] = None) -> Any:
    if seen is None:
        seen = set()
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= _MAX_STRING else value[:_MAX_STRING] + "...<truncated>"
    if depth >= _MAX_DEPTH:
        return {"__truncated__": True, "reason": "max_depth", "type": type(value).__name__}
    object_id = id(value)
    if object_id in seen:
        return {"__cycle__": True, "type": type(value).__name__}
    if isinstance(value, dict):
        seen.add(object_id)
        try:
            payload: Dict[str, Any] = {"__type__": "dict", "__len__": len(value)}
            for index, (key, nested) in enumerate(value.items()):
                if index >= _MAX_ITEMS:
                    payload["__truncated_items__"] = len(value) - _MAX_ITEMS
                    break
                payload[str(key)] = _safe_json(nested, depth=depth + 1, seen=seen)
            return payload
        finally:
            seen.discard(object_id)
    if isinstance(value, (list, tuple, set)):
        seen.add(object_id)
        try:
            items = list(value)
            payload_items = [_safe_json(item, depth=depth + 1, seen=seen) for item in items[:_MAX_ITEMS]]
            if len(items) > _MAX_ITEMS:
                payload_items.append({"__truncated_items__": len(items) - _MAX_ITEMS})
            return {"__type__": type(value).__name__, "__len__": len(items), "items": payload_items}
        finally:
            seen.discard(object_id)
    return {"__repr__": _safe_text(value), "__type__": type(value).__name__}


def _load_payload(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"ok": True, "source": _SOURCE, "events": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("source") == _SOURCE:
            return value
    except Exception:
        pass
    return {"ok": True, "source": _SOURCE, "events": []}


def _write_event(event: Mapping[str, Any]) -> Dict[str, Any]:
    path = _artifact_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_payload(path)
    events = list(payload.get("events") or [])
    events.append(dict(event))
    payload.update(
        {
            "ok": True,
            "source": _SOURCE,
            "installed": bool(_INSTALLED),
            "event_count": len(events),
            "events": events[-_MAX_EVENTS:],
        }
    )
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _empty_payload() -> Dict[str, object]:
    return {
        "ok": True,
        "source": _SOURCE,
        "installed": bool(_INSTALLED),
        "event_count": 0,
        "events": [],
        "module_summary": {
            "target_name_tokens": list(_TARGET_NAME_TOKENS),
            "trace_installed": bool(_INSTALLED),
        },
        "note": "trace probe installed around generated manual/apply-turn runtime functions",
    }


def write_runtime_apply_chain_probe_artifact() -> Dict[str, object]:
    path = _artifact_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and value.get("source") == _SOURCE:
                return value
        except Exception:
            pass
    payload = _empty_payload()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _candidate_result_zips(output_dir: Path) -> List[Path]:
    patterns = (
        "*interactive*campaign*results*.zip",
        "*autoplay*campaign*results*.zip",
        "*campaign*results*.zip",
        "*.zip",
    )
    candidates: List[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for path in output_dir.glob(pattern):
            if path.is_file() and path not in seen:
                candidates.append(path)
                seen.add(path)
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[:5]


def _zip_contains(zip_path: Path, member_name: str) -> bool:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            return member_name in set(zf.namelist())
    except Exception:
        return False


def append_runtime_apply_chain_probe_to_result_zips() -> Dict[str, object]:
    payload = write_runtime_apply_chain_probe_artifact()
    artifact = _artifact_path()
    output_dir = _diagnostic_output_dir()
    appended: List[str] = []
    for zip_path in _candidate_result_zips(output_dir):
        if _zip_contains(zip_path, ARTIFACT_NAME):
            continue
        try:
            with zipfile.ZipFile(zip_path, "a", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(artifact, arcname=ARTIFACT_NAME)
            appended.append(str(zip_path))
        except Exception:
            continue
    return {
        "ok": True,
        "source": _SOURCE,
        "artifact_path": str(artifact),
        "event_count": payload.get("event_count", 0) if isinstance(payload, dict) else 0,
        "zips_appended": appended,
    }


def _safe_frame(frame: FrameType) -> Dict[str, object]:
    code = frame.f_code
    return {
        "filename": str(code.co_filename)[-300:],
        "function_name": str(code.co_name)[-200:],
        "line_number": int(frame.f_lineno),
    }


def _safe_traceback_frames(tb: TracebackType | None) -> List[Dict[str, object]]:
    frames = traceback.extract_tb(tb, limit=120) if tb is not None else []
    return [
        {
            "filename": str(frame.filename)[-300:],
            "line_number": int(frame.lineno),
            "function_name": str(frame.name)[-200:],
            "line": _safe_text(frame.line or "", limit=500),
        }
        for frame in frames
    ]


def _interesting_locals(frame: FrameType) -> Dict[str, Any]:
    local_vars = frame.f_locals
    payload: Dict[str, Any] = {}
    for name in _INTERESTING_LOCAL_NAMES:
        if name in local_vars:
            payload[name] = _safe_json(local_vars[name])
    for name, value in local_vars.items():
        if name in payload:
            continue
        lowered = name.lower()
        if any(token in lowered for token in ("trace", "summary", "runtime", "error", "result", "intent")):
            payload[name] = _safe_json(value)
    return payload


def _payload_shape(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return {
            "type": "dict",
            "key_count": len(value),
            "keys": sorted(str(key) for key in value.keys())[:120],
            "has_error": "error" in value,
            "error_tail": _safe_text(value.get("error"), limit=500) if "error" in value else "",
            "has_traceback": "traceback" in value,
            "safe_excerpt": _safe_json(value, depth=0),
        }
    return {"type": type(value).__name__, "safe_excerpt": _safe_json(value, depth=0)}


def _should_trace_function(frame: FrameType) -> bool:
    code = frame.f_code
    name = code.co_name.lower()
    if not any(token in name for token in _TARGET_NAME_TOKENS):
        return False
    filename = str(code.co_filename)
    if "runtime_apply_chain_probe" in filename:
        return False
    return True


def _function_trace(frame: FrameType, event: str, arg: Any):
    started = frame.f_locals.get("__apply_chain_probe_started_at")
    if event == "return":
        duration = round(time.perf_counter() - started, 6) if isinstance(started, float) else None
        try:
            _write_event(
                {
                    "event_class": "runtime_apply_chain_return",
                    "source": _SOURCE,
                    "frame": _safe_frame(frame),
                    "duration_seconds": duration,
                    "locals": _interesting_locals(frame),
                    "return_payload_shape": _payload_shape(arg),
                }
            )
        except Exception:
            pass
    elif event == "exception":
        exc_type, exc, tb = arg if isinstance(arg, tuple) and len(arg) == 3 else (None, None, None)
        try:
            _write_event(
                {
                    "event_class": "runtime_apply_chain_exception",
                    "source": _SOURCE,
                    "frame": _safe_frame(frame),
                    "locals": _interesting_locals(frame),
                    "error_type": getattr(exc_type, "__name__", str(exc_type)) if exc_type is not None else "",
                    "message": _safe_text(exc, limit=1000),
                    "traceback_frames": _safe_traceback_frames(tb),
                }
            )
        except Exception:
            pass
    return _function_trace


def _runtime_apply_chain_trace(frame: FrameType, event: str, arg: Any):
    previous_result = None
    if callable(_PREVIOUS_TRACE):
        try:
            previous_result = _PREVIOUS_TRACE(frame, event, arg)
        except Exception:
            previous_result = None
    if event == "call" and _should_trace_function(frame):
        frame.f_locals["__apply_chain_probe_started_at"] = time.perf_counter()
        try:
            _write_event(
                {
                    "event_class": "runtime_apply_chain_enter",
                    "source": _SOURCE,
                    "frame": _safe_frame(frame),
                    "locals": _interesting_locals(frame),
                    "stack_tail": traceback.format_stack(limit=16),
                }
            )
        except Exception:
            pass
        return _function_trace
    return previous_result or _runtime_apply_chain_trace


def uninstall_runtime_apply_chain_probe() -> None:
    global _INSTALLED
    current = sys.gettrace()
    if current is _runtime_apply_chain_trace:
        sys.settrace(_PREVIOUS_TRACE)
    _INSTALLED = False


def install_runtime_apply_chain_probe_from_argv(argv: Iterable[str]) -> None:
    """Install a bounded trace probe for generated manual/apply-turn functions."""

    global _OUTPUT_DIR, _INSTALLED, _PREVIOUS_TRACE
    _OUTPUT_DIR = _output_dir_from_argv(argv)
    if _INSTALLED:
        return
    _PREVIOUS_TRACE = sys.gettrace()
    _INSTALLED = True
    sys.settrace(_runtime_apply_chain_trace)
    atexit.register(append_runtime_apply_chain_probe_to_result_zips)
    atexit.register(uninstall_runtime_apply_chain_probe)
    try:
        _write_event(
            {
                "event_class": "runtime_apply_chain_trace_installed",
                "source": _SOURCE,
                "target_name_tokens": list(_TARGET_NAME_TOKENS),
            }
        )
    except Exception:
        pass
