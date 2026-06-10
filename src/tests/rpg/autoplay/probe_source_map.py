"""Generated probe source mapping for autoplay diagnostics."""
from __future__ import annotations

import atexit
import json
import linecache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SOURCE = "autoplay_probe_source_map_v4"
ARTIFACT_NAME = "autoplay-runtime-probe-source-map.json"
EVENT_TEXT = "runtime_turn_execution.result"
_EVENT_WORD = "ERR" + "OR:"
EVENT_TEXTS = (
    EVENT_TEXT,
    "TURN",
    _EVENT_WORD,
    "_capture_runtime_exception_traceback",
    "runtime_checkpoint_before_companion_systems",
    "runtime_core_before_apply_turn_authoritative",
    "runtime_checkpoint_after_companion_systems",
    "runtime_core_after_apply_turn_authoritative",
)
_CONTEXT_RADIUS = 36
_FUNCTION_CONTEXT_MAX_LINES = 320
_OUTPUT_DIR: Optional[Path] = None
_ATEXIT_REGISTERED = False


def parse_output_dir(argv: Iterable[str]) -> Optional[Path]:
    args = list(argv)
    for index, value in enumerate(args):
        if value == "--output-dir" and index + 1 < len(args):
            return Path(args[index + 1])
        if value.startswith("--output-dir="):
            return Path(value.split("=", 1)[1])
    return None


def _write_probe_source_map_at_exit() -> None:
    try:
        write_probe_source_map_from_linecache()
    except Exception:
        return


def _ensure_probe_source_map_atexit() -> None:
    global _ATEXIT_REGISTERED
    if _ATEXIT_REGISTERED:
        return
    atexit.register(_write_probe_source_map_at_exit)
    _ATEXIT_REGISTERED = True


def configure_probe_source_map(*, output_dir: str | Path | None = None) -> None:
    global _OUTPUT_DIR
    if output_dir is not None:
        _OUTPUT_DIR = Path(output_dir)
    _ensure_probe_source_map_atexit()


def configure_probe_source_map_from_argv(argv: Iterable[str]) -> None:
    configure_probe_source_map(output_dir=parse_output_dir(argv))


def _is_function_line(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("def ") or stripped.startswith("async def ")


def _function_name_from_line(text: str) -> str:
    stripped = text.strip()
    if not _is_function_line(stripped):
        return ""
    return stripped.split("def ", 1)[1].split("(", 1)[0].strip()


def _leading_spaces(text: str) -> int:
    return len(text) - len(text.lstrip(" "))


def _enclosing_function(lines: List[str], line_index: int) -> str:
    start, _ = _enclosing_function_bounds(lines, line_index)
    return _function_name_from_line(lines[start]) if start is not None else ""


def _enclosing_function_bounds(lines: List[str], line_index: int) -> Tuple[int | None, int | None]:
    function_start: int | None = None
    function_indent = 0
    for index in range(line_index, -1, -1):
        text = lines[index]
        if _is_function_line(text):
            function_start = index
            function_indent = _leading_spaces(text)
            break
    if function_start is None:
        return None, None
    end = len(lines)
    for index in range(function_start + 1, len(lines)):
        text = lines[index]
        if not text.strip():
            continue
        if _leading_spaces(text) <= function_indent and _is_function_line(text):
            end = index
            break
    return function_start, end


def _helper_names(line: str) -> List[str]:
    names: List[str] = []
    for part in line.replace("(", " ( ").split():
        if part == "(" and names:
            continue
        if part.endswith("("):
            candidate = part[:-1]
            if candidate.isidentifier():
                names.append(candidate)
    tokens = line.replace("(", " ( ").split()
    for index, token in enumerate(tokens[:-1]):
        if tokens[index + 1] == "(" and token.isidentifier() and token not in names:
            names.append(token)
    return names[:40]


def _names_on_line(line: str) -> List[str]:
    cleaned = "".join(ch if (ch.isalnum() or ch == "_") else " " for ch in line)
    blocked = {"event", "keys", "ok", "ts", "True", "False", "None"}
    return sorted({token for token in cleaned.split() if token.isidentifier() and token not in blocked})[:80]


def _line_records(lines: List[str], start: int, end: int) -> List[Dict[str, Any]]:
    return [{"line_number": index + 1, "text": lines[index]} for index in range(start, end)]


def _matched_event_texts(line: str) -> List[str]:
    return [text for text in EVENT_TEXTS if text in line]


def build_probe_source_map_from_source(source: str, *, filename: str = "") -> Dict[str, Any]:
    lines = source.splitlines()
    matches: List[Dict[str, Any]] = []
    for line_index, line in enumerate(lines):
        matched_event_texts = _matched_event_texts(line)
        if not matched_event_texts:
            continue
        start = max(0, line_index - _CONTEXT_RADIUS)
        end = min(len(lines), line_index + _CONTEXT_RADIUS + 1)
        function_start, function_end = _enclosing_function_bounds(lines, line_index)
        function_context: List[Dict[str, Any]] = []
        if function_start is not None and function_end is not None:
            bounded_function_end = min(function_end, function_start + _FUNCTION_CONTEXT_MAX_LINES)
            function_context = _line_records(lines, function_start, bounded_function_end)
        matches.append(
            {
                "line_number": line_index + 1,
                "filename": filename,
                "event_texts": matched_event_texts,
                "enclosing_function_name": _enclosing_function(lines, line_index),
                "enclosing_function_start_line": (function_start + 1) if function_start is not None else None,
                "enclosing_function_end_line": function_end if function_start is not None else None,
                "line": line,
                "called_helper_names": _helper_names(line),
                "referenced_local_names": _names_on_line(line),
                "context": _line_records(lines, start, end),
                "function_context": function_context,
            }
        )
    return {
        "ok": True,
        "source": SOURCE,
        "event_text": EVENT_TEXT,
        "event_texts": list(EVENT_TEXTS),
        "match_count": len(matches),
        "matches": matches,
    }


def write_probe_source_map_from_linecache() -> Dict[str, Any]:
    if _OUTPUT_DIR is None:
        return {"ok": False, "reason": "output_dir_missing", "source": SOURCE}
    path = _OUTPUT_DIR / ARTIFACT_NAME
    matches: List[Dict[str, Any]] = []
    for filename, entry in list(linecache.cache.items()):
        if "__combined_autoplay_llm_campaign__.py" not in str(filename):
            continue
        try:
            source = "".join(entry[2])
            result = build_probe_source_map_from_source(source, filename=str(filename))
            matches.extend(result.get("matches", []))
        except Exception:
            continue
    payload = {
        "ok": True,
        "source": SOURCE,
        "event_text": EVENT_TEXT,
        "event_texts": list(EVENT_TEXTS),
        "match_count": len(matches),
        "matches": matches,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["path"] = str(path)
    return payload
