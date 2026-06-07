"""Result-path diagnostics for autoplay turn failures.

Phase 13.15 moved diagnostics from console interception to the actual saved
result payloads.  Phase 13.16 prioritizes trace-bearing runtime result payloads
so generic report ``ok: false`` objects cannot crowd out the real turn result
source before the bounded event cap is reached.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

SOURCE = "autoplay_result_path_diagnostics_v2"
SUMMARY_NAME = "autoplay-turn-error-diagnostics.json"
_TRACE_KEYS = {
    "manual_harness_trace",
    "manual_harness_trace_summary",
    "manual_stage_trace",
    "manual_stage_trace_summary",
    "manual_turn_summary",
    "narration_trace",
    "provider_trace",
    "runtime_name",
    "simulation_state",
    "turn_contract",
    "turn_perf_trace",
    "turn_perf_trace_summary",
}
_RUNTIME_KEYS = {
    "manual_harness_trace",
    "manual_harness_trace_summary",
    "manual_stage_trace",
    "manual_stage_trace_summary",
    "manual_turn_summary",
    "provider_trace",
    "runtime_name",
    "turn_contract",
    "turn_perf_trace",
    "turn_perf_trace_summary",
}
_ERROR_KEYS = {"error", "error_type", "exception", "exception_type", "traceback", "message"}
_GENERIC_EVENT_LIMIT = 300
_RUNTIME_EVENT_LIMIT = 800
_MAX_STRING = 2000
_MAX_JSON_FILES = 200
_MAX_ZIP_JSON_MEMBERS = 220


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _s(value: Any) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= _MAX_STRING else text[:_MAX_STRING] + "...<truncated>"


def _safe_json(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return {"__truncated__": True, "reason": "max_depth"}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _s(value)
    if isinstance(value, dict):
        return {str(k): _safe_json(v, depth=depth + 1) for k, v in list(value.items())[:80]}
    if isinstance(value, list):
        return [_safe_json(item, depth=depth + 1) for item in value[:80]]
    return _s(value)


def _load_json_text(text: str) -> Any:
    text = text.strip()
    if not text:
        return None
    return json.loads(text)


def _turn_index(payload: Mapping[str, Any], fallback: int | None = None) -> int | None:
    for key in ("turn_index", "turn", "turn_number", "tick"):
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        try:
            if value is not None:
                return int(value)
        except Exception:
            pass
    return fallback


def _has_error_marker(payload: Mapping[str, Any]) -> bool:
    if payload.get("ok") is False:
        return True
    if any(key in payload and payload.get(key) not in (None, "", [], {}) for key in _ERROR_KEYS):
        return True
    status = str(payload.get("status") or payload.get("result_status") or "").lower()
    return status in {"error", "failed", "failure"}


def _extract_error_fields(payload: Mapping[str, Any]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    for key in _ERROR_KEYS:
        if key in payload and payload.get(key) not in (None, "", [], {}):
            fields[key] = _safe_json(payload.get(key))
    for key in ("ok", "status", "result_status", "runtime_name", "player_input", "action", "source"):
        if key in payload:
            fields[key] = _safe_json(payload.get(key))
    return fields


def _extract_traces(payload: Mapping[str, Any]) -> Dict[str, Any]:
    traces: Dict[str, Any] = {}
    for key in _TRACE_KEYS:
        if key in payload and payload.get(key) not in (None, "", [], {}):
            traces[key] = _safe_json(payload.get(key))
    return traces


def _trace_keys(payload: Mapping[str, Any]) -> set[str]:
    return {key for key in _TRACE_KEYS if key in payload and payload.get(key) not in (None, "", [], {})}


def _is_runtime_result_payload(payload: Mapping[str, Any], traces: Mapping[str, Any] | None = None) -> bool:
    present = set(traces or {}) or _trace_keys(payload)
    if present & _RUNTIME_KEYS:
        return True
    runtime_name = str(payload.get("runtime_name") or "").lower()
    if runtime_name:
        return True
    source = str(payload.get("source") or "").lower()
    return "runtime" in source and ("turn" in source or "execution" in source)


def _walk(value: Any, *, path: str = "$", inherited_turn: int | None = None) -> Iterable[Tuple[str, Dict[str, Any], int | None]]:
    if isinstance(value, dict):
        turn = _turn_index(value, inherited_turn)
        yield path, value, turn
        for key, nested in value.items():
            if isinstance(nested, (dict, list)):
                yield from _walk(nested, path=f"{path}.{key}", inherited_turn=turn)
    elif isinstance(value, list):
        for index, nested in enumerate(value[:1000]):
            if isinstance(nested, (dict, list)):
                yield from _walk(nested, path=f"{path}[{index}]", inherited_turn=inherited_turn)


def _event_priority(event: Mapping[str, Any]) -> tuple[int, int, str]:
    traces = set(event.get("trace_keys_present") or [])
    trace_score = len(traces & _RUNTIME_KEYS)
    runtime_bonus = 10 if event.get("runtime_result") else 0
    turn_bonus = 2 if event.get("turn_index") is not None else 0
    return (runtime_bonus + trace_score + turn_bonus, trace_score, str(event.get("json_path") or ""))


def extract_result_path_events(value: Any, *, source_path: str = "") -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    seen: set[tuple[str, int | None]] = set()
    for path, payload, turn in _walk(value):
        if not _has_error_marker(payload):
            continue
        key = (path, turn)
        if key in seen:
            continue
        seen.add(key)
        traces = _extract_traces(payload)
        runtime_result = _is_runtime_result_payload(payload, traces)
        error_fields = _extract_error_fields(payload)
        events.append(
            {
                "turn_index": turn,
                "json_path": path,
                "source_path": source_path,
                "runtime_result": runtime_result,
                "event_class": "runtime_result" if runtime_result else "generic_failure",
                "error_fields": error_fields,
                "traces": traces,
                "trace_keys_present": sorted(traces),
                "source": SOURCE,
            }
        )
    events.sort(key=_event_priority, reverse=True)
    return events


def split_result_path_events(events: Iterable[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    runtime_events: List[Dict[str, Any]] = []
    generic_events: List[Dict[str, Any]] = []
    seen_runtime: set[tuple[str, str, int | None]] = set()
    seen_generic: set[tuple[str, str, int | None]] = set()
    for event in events:
        normalized = dict(event)
        key = (
            str(normalized.get("source_path") or ""),
            str(normalized.get("json_path") or ""),
            normalized.get("turn_index"),
        )
        if normalized.get("runtime_result"):
            if key in seen_runtime:
                continue
            seen_runtime.add(key)
            runtime_events.append(normalized)
        else:
            if key in seen_generic:
                continue
            seen_generic.add(key)
            generic_events.append(normalized)
    runtime_events.sort(key=_event_priority, reverse=True)
    generic_events.sort(key=_event_priority, reverse=True)
    return {
        "runtime_result_events": runtime_events[:_RUNTIME_EVENT_LIMIT],
        "generic_failure_events": generic_events[:_GENERIC_EVENT_LIMIT],
    }


def _candidate_json_files(output_dir: Path) -> List[Path]:
    if not output_dir.exists():
        return []
    files = [path for path in output_dir.rglob("*.json") if path.is_file()]
    preferred = ("transcript", "summary", "performance", "runtime", "turn")
    files.sort(
        key=lambda path: (
            0 if any(part in path.name.lower() for part in preferred) else 1,
            -path.stat().st_mtime,
        )
    )
    return files[:_MAX_JSON_FILES]


def _collect_all_events_from_value(value: Any, *, source_path: str, events: List[Dict[str, Any]]) -> None:
    events.extend(extract_result_path_events(value, source_path=source_path))


def collect_result_path_diagnostics(output_dir: str | Path, *, zip_path: str | Path | None = None) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    events: List[Dict[str, Any]] = []
    scanned: List[str] = []
    for path in _candidate_json_files(output_dir):
        if path.name == SUMMARY_NAME:
            continue
        try:
            value = _load_json_text(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        scanned.append(str(path))
        _collect_all_events_from_value(value, source_path=str(path), events=events)
    if zip_path and Path(zip_path).exists():
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = [name for name in zf.namelist() if name.lower().endswith(".json")]
                names.sort(key=lambda name: 0 if any(part in name.lower() for part in ("transcript", "summary", "performance", "runtime", "turn")) else 1)
                for name in names[:_MAX_ZIP_JSON_MEMBERS]:
                    if name.endswith(SUMMARY_NAME):
                        continue
                    try:
                        value = _load_json_text(zf.read(name).decode("utf-8"))
                    except Exception:
                        continue
                    source = f"{zip_path}:{name}"
                    scanned.append(source)
                    _collect_all_events_from_value(value, source_path=source, events=events)
        except Exception:
            pass
    split = split_result_path_events(events)
    runtime_events = split["runtime_result_events"]
    generic_events = split["generic_failure_events"]
    combined_events = [*runtime_events, *generic_events]
    return {
        "ok": True,
        "source": SOURCE,
        "runtime_result_event_count": len(runtime_events),
        "generic_failure_event_count": len(generic_events),
        "event_count": len(combined_events),
        "runtime_result_events": runtime_events,
        "generic_failure_events": generic_events,
        "events": combined_events,
        "scanned_sources": scanned[: _MAX_JSON_FILES + _MAX_ZIP_JSON_MEMBERS],
    }


def write_result_path_diagnostics(output_dir: str | Path, *, zip_path: str | Path | None = None) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = collect_result_path_diagnostics(output_dir, zip_path=zip_path)
    path = output_dir / SUMMARY_NAME
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["path"] = str(path)
    return payload
