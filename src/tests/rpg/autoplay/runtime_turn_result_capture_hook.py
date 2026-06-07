"""Capture runtime turn result probe emissions for autoplay evidence.

The generated autoplay harness emits ``event=runtime_turn_execution.result``
through the console probe path before the result is flattened into text.  This
hook wraps stdout/stderr writes before generated fragments load and persists the
emitted runtime-result lines as structured evidence.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, TextIO

SOURCE = "autoplay_runtime_turn_result_capture_hook_v1"
ARTIFACT_NAME = "autoplay-runtime-turn-results.json"
_INSTALLED = False
_OUTPUT_DIR: Optional[Path] = None
_ORIGINAL_STDOUT: Optional[TextIO] = None
_ORIGINAL_STDERR: Optional[TextIO] = None
_EVENT_PATTERN = "event=runtime_turn_execution.result"
_TOKEN_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>[^\s]+)")


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


def parse_runtime_turn_result_line(line: str) -> Dict[str, Any]:
    tokens = {match.group("key"): match.group("value") for match in _TOKEN_RE.finditer(line)}
    keys = [key for key in tokens.get("keys", "").split(",") if key]
    event: Dict[str, Any] = {
        "runtime_result": True,
        "event_class": "runtime_result_emission",
        "source": SOURCE,
        "line": line[-4000:],
        "tokens": tokens,
        "trace_keys_present": sorted(
            key
            for key in keys
            if key
            in {
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
        ),
        "result_keys": keys,
    }
    if "ok" in tokens:
        event["ok"] = tokens["ok"].lower() == "true"
    if "turn" in tokens:
        try:
            event["turn_index"] = int(tokens["turn"])
        except Exception:
            pass
    if "turn_index" in tokens:
        try:
            event["turn_index"] = int(tokens["turn_index"])
        except Exception:
            pass
    return event


def record_runtime_turn_result_line(line: str) -> None:
    if _EVENT_PATTERN not in line:
        return
    path = _artifact_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_payload(path)
    events = list(payload.get("events") or [])
    events.append(parse_runtime_turn_result_line(line))
    payload.update(
        {
            "ok": True,
            "source": SOURCE,
            "event_count": len(events),
            "events": events[-1000:],
        }
    )
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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
