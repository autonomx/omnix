"""Result-path diagnostics for autoplay turn failures.

Phase 13.15 moves diagnostics from console interception to the actual saved
result payloads.  The scanner is intentionally schema-tolerant because the live
harness stores traces in generated artifacts with evolving key names.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

SOURCE = "autoplay_result_path_diagnostics_v1"
SUMMARY_NAME = "autoplay-turn-error-diagnostics.json"
_TRACE_KEYS = {
    "manual_harness_trace",
    "manual_harness_trace_summary",
    "manual_stage_trace",
    "manual_turn_summary",
    "narration_trace",
    "provider_trace",
    "turn_perf_trace",
    "turn_perf_trace_summary",
}
_ERROR_KEYS = {"error", "error_type", "exception", "exception_type", "traceback", "message"}
_MAX_EVENTS = 300
_MAX_STRING = 2000
_MAX_JSON_FILES = 160
_MAX_ZIP_JSON_MEMBERS = 160


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


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
        error_fields = _extract_error_fields(payload)
        events.append(
            {
                "turn_index": turn,
                "json_path": path,
                "source_path": source_path,
                "error_fields": error_fields,
                "traces": traces,
                "trace_keys_present": sorted(traces),
                "source": SOURCE,
            }
        )
        if len(events) >= _MAX_EVENTS:
            break
    return events


def _candidate_json_files(output_dir: Path) -> List[Path]:
    if not output_dir.exists():
        return []
    files = [path for path in output_dir.rglob("*.json") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[:_MAX_JSON_FILES]


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
        events.extend(extract_result_path_events(value, source_path=str(path)))
        if len(events) >= _MAX_EVENTS:
            break
    if len(events) < _MAX_EVENTS and zip_path and Path(zip_path).exists():
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = [name for name in zf.namelist() if name.lower().endswith(".json")]
                for name in names[:_MAX_ZIP_JSON_MEMBERS]:
                    if name.endswith(SUMMARY_NAME):
                        continue
                    try:
                        value = _load_json_text(zf.read(name).decode("utf-8"))
                    except Exception:
                        continue
                    scanned.append(f"{zip_path}:{name}")
                    events.extend(extract_result_path_events(value, source_path=f"{zip_path}:{name}"))
                    if len(events) >= _MAX_EVENTS:
                        break
        except Exception:
            pass
    return {
        "ok": True,
        "source": SOURCE,
        "event_count": len(events[:_MAX_EVENTS]),
        "events": events[:_MAX_EVENTS],
        "scanned_sources": scanned[:_MAX_EVENTS],
    }


def write_result_path_diagnostics(output_dir: str | Path, *, zip_path: str | Path | None = None) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = collect_result_path_diagnostics(output_dir, zip_path=zip_path)
    path = output_dir / SUMMARY_NAME
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["path"] = str(path)
    return payload
