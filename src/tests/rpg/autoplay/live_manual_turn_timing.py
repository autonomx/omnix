"""Live manual-turn substage timing for autoplay diagnostics."""
from __future__ import annotations

import functools
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional

SOURCE = "autoplay_live_manual_turn_timing_v1"
ARTIFACT_NAME = "autoplay-live-manual-turn-substage-timing.json"
_OUTPUT_DIR: Optional[Path] = None
_WRAPPED_NAMES: set[str] = set()

_STAGE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pre_runtime_intent_llm_ms", ("intent", "classif", "player_agent", "pre_runtime")),
    ("deterministic_runtime_apply_ms", ("deterministic", "apply", "simulate", "simulation")),
    ("grounding_validation_ms", ("ground", "validat", "validator")),
    ("repair_ms", ("repair", "retry", "fallback")),
)
_EXCLUDE_TOKENS = (
    "main",
    "runner",
    "autoplay_runner",
    "run_autoplay",
    "assert",
    "facade",
    "manifest",
    "wrapper",
    "report",
    "artifact",
    "zip",
    "html",
    "scan",
    "extract",
    "collect",
    "load",
    "write",
    "render",
    "append",
)
_EXCLUDE_MODULE_TOKENS = (
    "autoplay_performance_artifacts",
    "live_performance_bridge",
    "performance_artifacts",
    "result_path_diagnostics",
    "runtime_turn_result_capture_hook",
    "survival_report_artifacts",
    "survival_report_writer_hook",
)
_EXCLUDE_FILENAME_TOKENS = tuple(token.replace(".", "/") for token in _EXCLUDE_MODULE_TOKENS)


def parse_output_dir(argv: Iterable[str]) -> Optional[Path]:
    args = list(argv)
    for index, value in enumerate(args):
        if value == "--output-dir" and index + 1 < len(args):
            return Path(args[index + 1])
        if value.startswith("--output-dir="):
            return Path(value.split("=", 1)[1])
    return None


def configure_live_manual_turn_timing(*, output_dir: str | Path | None = None) -> None:
    global _OUTPUT_DIR
    if output_dir is not None:
        _OUTPUT_DIR = Path(output_dir)


def configure_live_manual_turn_timing_from_argv(argv: Iterable[str]) -> None:
    configure_live_manual_turn_timing(output_dir=parse_output_dir(argv))


def _excluded_by_code_location(value: Any) -> bool:
    module = str(getattr(value, "__module__", "") or "").lower()
    if any(token in module for token in _EXCLUDE_MODULE_TOKENS):
        return True
    code = getattr(value, "__code__", None)
    filename = str(getattr(code, "co_filename", "") or "").replace("\\", "/").lower()
    return any(token in filename for token in _EXCLUDE_FILENAME_TOKENS)


def classify_stage_name(function_name: str) -> str | None:
    lowered = function_name.lower()
    if any(token in lowered for token in _EXCLUDE_TOKENS):
        return None
    for stage, tokens in _STAGE_RULES:
        if any(token in lowered for token in tokens):
            return stage
    return None


def should_wrap_timing_function(name: str, value: Any) -> bool:
    if not callable(value) or getattr(value, "__autoplay_live_timing_wrapped__", False):
        return False
    if classify_stage_name(name) is None:
        return False
    if _excluded_by_code_location(value):
        return False
    code = getattr(value, "__code__", None)
    if code is None:
        return False
    return len(getattr(code, "co_code", b"")) >= 80


def _turn_index_from_args(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> int | None:
    for key in ("turn_index", "turn", "turn_number", "tick"):
        raw = kwargs.get(key)
        try:
            if raw is not None:
                return int(raw)
        except Exception:
            pass
    for value in args:
        if isinstance(value, dict):
            for key in ("turn_index", "turn", "turn_number", "tick"):
                raw = value.get(key)
                try:
                    if raw is not None:
                        return int(raw)
                except Exception:
                    pass
    return None


def _load_payload(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"ok": True, "source": SOURCE, "events": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"ok": True, "source": SOURCE, "events": []}
    except Exception:
        return {"ok": True, "source": SOURCE, "events": []}


def record_substage_timing(stage_name: str, function_name: str, elapsed_ms: float, *, turn_index: int | None = None) -> Dict[str, Any]:
    if _OUTPUT_DIR is None:
        return {"ok": False, "reason": "output_dir_missing", "source": SOURCE}
    path = _OUTPUT_DIR / ARTIFACT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_payload(path)
    events = list(payload.get("events") or [])
    events.append(
        {
            "stage_name": stage_name,
            "function_name": function_name,
            "elapsed_ms": round(float(elapsed_ms), 3),
            "turn_index": turn_index,
            "source": SOURCE,
        }
    )
    events = events[-5000:]
    stage_summary: Dict[str, Dict[str, Any]] = {}
    for event in events:
        stage = str(event.get("stage_name") or "")
        if not stage:
            continue
        entry = stage_summary.setdefault(stage, {"count": 0, "total_ms": 0.0, "max_ms": 0.0})
        elapsed = float(event.get("elapsed_ms") or 0.0)
        entry["count"] += 1
        entry["total_ms"] += elapsed
        entry["max_ms"] = max(float(entry.get("max_ms") or 0.0), elapsed)
    for entry in stage_summary.values():
        count = int(entry.get("count") or 0)
        entry["avg_ms"] = round(float(entry.get("total_ms") or 0.0) / count, 3) if count else None
        entry["total_ms"] = round(float(entry.get("total_ms") or 0.0), 3)
    payload.update({"ok": True, "source": SOURCE, "event_count": len(events), "events": events, "stage_summary": stage_summary})
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["path"] = str(path)
    return payload


def wrap_live_manual_turn_timing_functions(namespace: MutableMapping[str, Any]) -> Dict[str, Any]:
    wrapped: List[str] = []
    for name, value in list(namespace.items()):
        if name in _WRAPPED_NAMES or not should_wrap_timing_function(name, value):
            continue
        stage = classify_stage_name(name)
        if stage is None:
            continue
        try:
            @functools.wraps(value)
            def wrapper(*args: Any, __original: Callable[..., Any] = value, __name: str = name, __stage: str = stage, **kwargs: Any) -> Any:
                started = time.perf_counter()
                try:
                    return __original(*args, **kwargs)
                finally:
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    try:
                        record_substage_timing(__stage, __name, elapsed_ms, turn_index=_turn_index_from_args(args, kwargs))
                    except Exception:
                        pass
            wrapper.__autoplay_live_timing_wrapped__ = True  # type: ignore[attr-defined]
            namespace[name] = wrapper
            _WRAPPED_NAMES.add(name)
            wrapped.append(name)
        except Exception:
            continue
    return {"ok": True, "source": SOURCE, "wrapped_count": len(wrapped), "wrapped_names": wrapped}
