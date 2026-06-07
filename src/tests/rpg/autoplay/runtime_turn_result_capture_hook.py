"""Capture runtime turn result probe emissions for autoplay evidence.

The generated autoplay harness emits ``event=runtime_turn_execution.result``
through the console probe path before the result is flattened into text.  The
live stream hook is best-effort because the generated harness may capture output
through its own stream layer; Phase 13.18 therefore also parses the persisted
console log after the run and backfills this artifact from that source.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, TextIO

SOURCE = "autoplay_runtime_turn_result_capture_hook_v2"
ARTIFACT_NAME = "autoplay-runtime-turn-results.json"
_INSTALLED = False
_OUTPUT_DIR: Optional[Path] = None
_ORIGINAL_STDOUT: Optional[TextIO] = None
_ORIGINAL_STDERR: Optional[TextIO] = None
_EVENT_PATTERN = "event=runtime_turn_execution.result"
_TOKEN_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>[^\s]+)")
_TIMESTAMP_RE = re.compile(r"ts=(?P<ts>[^\s]+)")


def _parse_output_dir(argv: Iterable[str]) -> Optional[Path]:
    args = list(argv)
    for index, value in enumerate(args):
        if value == "--output-dir" and index + 1 < len(args):
            return Path(args[index + 1])
        if value.startswith("--output-dir="):
            return Path(value.split("=", 1)[1])
    return None


def _artifact_path() -> Optional[Path]:
    return (_OUTPUT_DIR / ARTIFACT_NAME) if _OUTPUT_DIR is not None else None


def _load_payload(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"ok": True, "source": SOURCE, "events": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"ok": True, "source": SOURCE, "events": []}
    except Exception:
        return {"ok": True, "source": SOURCE, "events": []}


def _runtime_trace_key_set() -> set[str]:
    return {
        "manual_harness_trace",
        "manual_harness_trace_summary",
        "manual_stage_trace",
        "manual_turn_summary",
        "narration_trace",
        "provider_trace",
        "runtime_name",
        "turn_contract",
        "turn_perf_trace",
        "turn_perf_trace_summary",
    }


def parse_runtime_turn_result_line(line: str, *, capture_source: str = "stream") -> Dict[str, Any]:
    tokens = {match.group("key"): match.group("value") for match in _TOKEN_RE.finditer(line)}
    keys = [key for key in tokens.get("keys", "").split(",") if key]
    timestamp_match = _TIMESTAMP_RE.search(line)
    event: Dict[str, Any] = {
        "runtime_result": True,
        "event_class": "runtime_result_emission",
        "capture_source": capture_source,
        "source": SOURCE,
        "line": line[-4000:],
        "tokens": tokens,
        "trace_keys_present": sorted(key for key in keys if key in _runtime_trace_key_set()),
        "result_keys": keys,
    }
    if timestamp_match:
        event["timestamp"] = timestamp_match.group("ts")
    if "ok" in tokens:
        event["ok"] = tokens["ok"].lower() == "true"
    for turn_key in ("turn", "turn_index"):
        if turn_key in tokens:
            try:
                event["turn_index"] = int(tokens[turn_key])
                break
            except Exception:
                pass
    return event


def _dedupe_events(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[Any, str, str]] = set()
    for event in events:
        key = (
            event.get("turn_index"),
            str(event.get("capture_source") or ""),
            str(event.get("line") or "")[-500:],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped


def _write_events(path: Path, events: Iterable[Dict[str, Any]], *, backfill_source: str | None = None) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_payload(path)
    merged = _dedupe_events([*(existing.get("events") or []), *events])
    payload: Dict[str, Any] = {
        "ok": True,
        "source": SOURCE,
        "event_count": len(merged),
        "events": merged[-1000:],
    }
    if backfill_source:
        payload["backfill_source"] = backfill_source
        payload["backfilled_from_console_log"] = True
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def record_runtime_turn_result_line(line: str) -> None:
    if _EVENT_PATTERN not in line:
        return
    path = _artifact_path()
    if path is None:
        return
    _write_events(path, [parse_runtime_turn_result_line(line, capture_source="stream")])


def parse_console_log_runtime_turn_results(console_log_path: str | Path) -> List[Dict[str, Any]]:
    path = Path(console_log_path)
    if not path.exists():
        return []
    events: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if _EVENT_PATTERN in line:
                    events.append(parse_runtime_turn_result_line(line.rstrip("\n"), capture_source="console_log"))
    except Exception:
        return events
    return _dedupe_events(events)


def backfill_runtime_turn_results_from_console_log(output_dir: str | Path) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    console_candidates = [
        output_dir / "console-log.txt",
        output_dir / "autoplay-console-log.txt",
        output_dir / "autoplay-campaign-results-unzipped" / "console-log.txt",
    ]
    for console_path in console_candidates:
        events = parse_console_log_runtime_turn_results(console_path)
        if events:
            payload = _write_events(
                output_dir / ARTIFACT_NAME,
                events,
                backfill_source=str(console_path),
            )
            payload["path"] = str(output_dir / ARTIFACT_NAME)
            return payload
    path = output_dir / ARTIFACT_NAME
    if path.exists():
        payload = _load_payload(path)
        payload["path"] = str(path)
        payload.setdefault("event_count", len(payload.get("events") or []))
        return payload
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"ok": True, "source": SOURCE, "event_count": 0, "events": [], "path": str(path)}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


class _CaptureStream:
    def __init__(self, wrapped: TextIO):
        self._wrapped = wrapped
        self._buffer = ""

    def write(self, text: str) -> int:
        written = self._wrapped.write(text)
        self._buffer += str(text)
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            try:
                record_runtime_turn_result_line(line)
            except Exception:
                pass
        return written

    def flush(self) -> None:
        self._wrapped.flush()
        if self._buffer:
            try:
                record_runtime_turn_result_line(self._buffer)
            except Exception:
                pass
            self._buffer = ""

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)


def install_runtime_turn_result_capture_hook(*, output_dir: str | Path | None = None) -> bool:
    global _INSTALLED, _OUTPUT_DIR, _ORIGINAL_STDOUT, _ORIGINAL_STDERR
    if output_dir is not None:
        _OUTPUT_DIR = Path(output_dir)
    if _INSTALLED:
        return False
    _ORIGINAL_STDOUT = sys.stdout
    _ORIGINAL_STDERR = sys.stderr
    sys.stdout = _CaptureStream(sys.stdout)  # type: ignore[assignment]
    sys.stderr = _CaptureStream(sys.stderr)  # type: ignore[assignment]
    _INSTALLED = True
    return True


def install_runtime_turn_result_capture_hook_from_argv(argv: Iterable[str]) -> bool:
    return install_runtime_turn_result_capture_hook(output_dir=_parse_output_dir(argv))
