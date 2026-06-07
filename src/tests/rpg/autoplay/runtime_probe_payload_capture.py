"""Capture full runtime probe payload context for autoplay evidence.

Phase 13.18 proved the runtime-result probe line is present in the persisted
console log, but only as flattened text.  Phase 13.19 instruments generated
runtime source around the probe line and wraps probe helper functions after load
so bounded locals/arguments can be persisted before the payload is flattened.
"""
from __future__ import annotations

import functools
import inspect
import json
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Optional

SOURCE = "autoplay_runtime_probe_payload_capture_v1"
ARTIFACT_NAME = "autoplay-runtime-turn-result-payloads.json"
_EVENT_NAME = "runtime_turn_execution.result"
_MAX_EVENTS = 1000
_MAX_DEPTH = 8
_MAX_ITEMS = 120
_MAX_STRING = 4000
_OUTPUT_DIR: Optional[Path] = None
_WRAPPED_NAMES: set[str] = set()


def parse_output_dir(argv: Iterable[str]) -> Optional[Path]:
    args = list(argv)
    for index, value in enumerate(args):
        if value == "--output-dir" and index + 1 < len(args):
            return Path(args[index + 1])
        if value.startswith("--output-dir="):
            return Path(value.split("=", 1)[1])
    return None


def configure_runtime_probe_payload_capture(*, output_dir: str | Path | None = None) -> None:
    global _OUTPUT_DIR
    if output_dir is not None:
        _OUTPUT_DIR = Path(output_dir)


def configure_runtime_probe_payload_capture_from_argv(argv: Iterable[str]) -> None:
    configure_runtime_probe_payload_capture(output_dir=parse_output_dir(argv))


def artifact_path() -> Optional[Path]:
    return (_OUTPUT_DIR / ARTIFACT_NAME) if _OUTPUT_DIR is not None else None


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
    if isinstance(value, (dict, list, tuple, set)):
        seen.add(object_id)
        try:
            if isinstance(value, dict):
                payload: Dict[str, Any] = {}
                for index, (key, nested) in enumerate(value.items()):
                    if index >= _MAX_ITEMS:
                        payload["__truncated_items__"] = len(value) - _MAX_ITEMS
                        break
                    payload[str(key)] = _safe_json(nested, depth=depth + 1, seen=seen)
                return payload
            items = list(value)
            payload_items = [_safe_json(item, depth=depth + 1, seen=seen) for item in items[:_MAX_ITEMS]]
            if len(items) > _MAX_ITEMS:
                payload_items.append({"__truncated_items__": len(items) - _MAX_ITEMS})
            return payload_items
        finally:
            seen.discard(object_id)
    return repr(value)


def _load_payload(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"ok": True, "source": SOURCE, "events": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"ok": True, "source": SOURCE, "events": []}
    except Exception:
        return {"ok": True, "source": SOURCE, "events": []}


def _write_event(event: Mapping[str, Any]) -> Dict[str, Any]:
    path = artifact_path()
    if path is None:
        return {"ok": False, "reason": "output_dir_missing", "source": SOURCE}
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_payload(path)
    events = list(payload.get("events") or [])
    events.append(dict(event))
    payload.update({"ok": True, "source": SOURCE, "event_count": len(events), "events": events[-_MAX_EVENTS:]})
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["path"] = str(path)
    return payload


def _turn_index_from_value(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    for key in ("turn_index", "turn", "turn_number", "tick"):
        raw = value.get(key)
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        try:
            if raw is not None:
                return int(raw)
        except Exception:
            pass
    return None


def _interesting_locals(local_vars: Mapping[str, Any]) -> Dict[str, Any]:
    wanted: Dict[str, Any] = {}
    preferred_names = (
        "turn_index",
        "turn",
        "turn_number",
        "player_input",
        "player_action",
        "runtime_name",
        "turn_result",
        "result",
        "runtime_result",
        "manual_harness_trace",
        "manual_harness_trace_summary",
        "manual_stage_trace",
        "manual_turn_summary",
        "provider_trace",
        "turn_contract",
        "turn_perf_trace",
        "turn_perf_trace_summary",
    )
    for name in preferred_names:
        if name in local_vars:
            wanted[name] = _safe_json(local_vars[name])
    for name, value in local_vars.items():
        if name in wanted:
            continue
        if any(token in name for token in ("trace", "runtime", "turn_contract", "turn_perf", "manual_")):
            wanted[name] = _safe_json(value)
    return wanted


def capture_runtime_probe_locals(local_vars: Mapping[str, Any], *, source_label: str = "source_instrumentation") -> Dict[str, Any]:
    local_copy = dict(local_vars)
    event = {
        "event_class": "runtime_probe_locals",
        "runtime_result": True,
        "source": SOURCE,
        "capture_source": source_label,
        "turn_index": _turn_index_from_value(local_copy) or _turn_index_from_value(local_copy.get("turn_result")) or _turn_index_from_value(local_copy.get("result")),
        "locals": _interesting_locals(local_copy),
        "available_local_names": sorted(str(key) for key in local_copy.keys())[:200],
        "stack_tail": traceback.format_stack(limit=12),
    }
    return _write_event(event)


def _value_contains_event(value: Any) -> bool:
    if value == _EVENT_NAME:
        return True
    if isinstance(value, str):
        return _EVENT_NAME in value
    if isinstance(value, dict):
        return any(_value_contains_event(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_value_contains_event(item) for item in value)
    return False


def _probe_payload_from_call(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "args": _safe_json(list(args)),
        "kwargs": _safe_json(dict(kwargs)),
        "turn_index": _turn_index_from_value(kwargs) or next((_turn_index_from_value(arg) for arg in args if isinstance(arg, dict)), None),
    }


def should_wrap_probe_function(name: str, value: Any) -> bool:
    if not callable(value) or getattr(value, "__autoplay_probe_payload_wrapped__", False):
        return False
    lowered = name.lower()
    if "probe" in lowered or "stage" in lowered or "trace" in lowered:
        return True
    code = getattr(value, "__code__", None)
    if code is not None:
        constants = getattr(code, "co_consts", ()) or ()
        names = getattr(code, "co_names", ()) or ()
        return any(_value_contains_event(constant) for constant in constants) or any("probe" in str(item).lower() for item in names)
    return False


def wrap_runtime_probe_functions(namespace: MutableMapping[str, Any]) -> Dict[str, Any]:
    wrapped: list[str] = []
    for name, value in list(namespace.items()):
        if name in _WRAPPED_NAMES or not should_wrap_probe_function(name, value):
            continue
        try:
            @functools.wraps(value)
            def wrapper(*args: Any, __original: Callable[..., Any] = value, __name: str = name, **kwargs: Any) -> Any:
                if _value_contains_event(args) or _value_contains_event(kwargs):
                    _write_event(
                        {
                            "event_class": "runtime_probe_call",
                            "runtime_result": True,
                            "source": SOURCE,
                            "capture_source": "probe_function_wrapper",
                            "function_name": __name,
                            "payload": _probe_payload_from_call(args, kwargs),
                            "signature": str(inspect.signature(__original)) if callable(__original) else "",
                            "stack_tail": traceback.format_stack(limit=12),
                        }
                    )
                return __original(*args, **kwargs)
            wrapper.__autoplay_probe_payload_wrapped__ = True  # type: ignore[attr-defined]
            namespace[name] = wrapper
            _WRAPPED_NAMES.add(name)
            wrapped.append(name)
        except Exception:
            continue
    return {"ok": True, "source": SOURCE, "wrapped_count": len(wrapped), "wrapped_names": wrapped}


def instrument_runtime_probe_source(source: str) -> str:
    """Inject a locals capture before lines containing the runtime result event."""
    lines = source.splitlines()
    instrumented: list[str] = []
    for line in lines:
        if _EVENT_NAME in line and "capture_runtime_probe_locals" not in line:
            indent = line[: len(line) - len(line.lstrip())]
            instrumented.append(indent + "try:")
            instrumented.append(indent + "    from tests.rpg.autoplay.runtime_probe_payload_capture import capture_runtime_probe_locals")
            instrumented.append(indent + "    capture_runtime_probe_locals(locals())")
            instrumented.append(indent + "except Exception:")
            instrumented.append(indent + "    pass")
        instrumented.append(line)
    return "\n".join(instrumented) + ("\n" if source.endswith("\n") else "")
