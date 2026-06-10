"""Live manual-turn substage timing for autoplay diagnostics."""
from __future__ import annotations

import functools
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional

SOURCE = "autoplay_live_manual_turn_timing_v1"
ARTIFACT_NAME = "autoplay-live-manual-turn-substage-timing.json"
RUNTIME_CHAIN_SOURCE = "autoplay_runtime_apply_chain_probe_v1"
RUNTIME_CHAIN_ARTIFACT_NAME = "autoplay-runtime-apply-chain-probe.json"
_OUTPUT_DIR: Optional[Path] = None
_WRAPPED_NAMES: set[str] = set()
_RUNTIME_CHAIN_WRAPPED: set[str] = set()

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
    "bundle",
    "static_actions",
)
_ALLOWED_STAGE_FUNCTION_NAMES = {
    "call_pre_runtime_intent_llm": "pre_runtime_intent_llm_ms",
    "deterministic_runtime_apply_state": "deterministic_runtime_apply_ms",
    "run_grounding_validator": "grounding_validation_ms",
    "repair_intent_payload": "repair_ms",
}
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


def _safe_tail(value: object, *, limit: int = 500) -> str:
    try:
        return str(value)[-limit:]
    except Exception as exc:
        return type(exc).__name__


def _excluded_by_code_location(value: Any) -> bool:
    module = str(getattr(value, "__module__", "") or "").lower()
    if any(token in module for token in _EXCLUDE_MODULE_TOKENS):
        return True
    code = getattr(value, "__code__", None)
    filename = str(getattr(code, "co_filename", "") or "").replace("\\", "/").lower()
    return any(token in filename for token in _EXCLUDE_FILENAME_TOKENS)


def classify_stage_name(function_name: str) -> str | None:
    lowered = function_name.lower()
    if lowered.startswith("_"):
        return None
    if lowered in _ALLOWED_STAGE_FUNCTION_NAMES:
        return _ALLOWED_STAGE_FUNCTION_NAMES[lowered]
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


def _load_payload(path: Path, *, source: str = SOURCE) -> Dict[str, Any]:
    if not path.exists():
        return {"ok": True, "source": source, "events": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"ok": True, "source": source, "events": []}
    except Exception:
        return {"ok": True, "source": source, "events": []}


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


def record_runtime_apply_chain_event(
    *,
    module_name: str,
    function_name: str,
    elapsed_ms: float,
    ok: bool,
    error: BaseException | None = None,
) -> Dict[str, Any]:
    if _OUTPUT_DIR is None:
        return {"ok": False, "reason": "output_dir_missing", "source": RUNTIME_CHAIN_SOURCE}
    path = _OUTPUT_DIR / RUNTIME_CHAIN_ARTIFACT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_payload(path, source=RUNTIME_CHAIN_SOURCE)
    events = list(payload.get("events") or [])
    event = {
        "module_name": module_name,
        "function_name": function_name,
        "elapsed_ms": round(float(elapsed_ms), 3),
        "ok": bool(ok),
        "source": RUNTIME_CHAIN_SOURCE,
    }
    if error is not None:
        event["error_type"] = type(error).__name__
        event["error_tail"] = _safe_tail(error)
    events.append(event)
    events = events[-10000:]
    module_summary: Dict[str, Dict[str, Any]] = {}
    for item in events:
        module = str(item.get("module_name") or "")
        if not module:
            continue
        entry = module_summary.setdefault(module, {"count": 0, "error_count": 0, "max_ms": 0.0})
        entry["count"] += 1
        if item.get("ok") is not True:
            entry["error_count"] += 1
        entry["max_ms"] = max(float(entry.get("max_ms") or 0.0), float(item.get("elapsed_ms") or 0.0))
    payload.update({"ok": True, "source": RUNTIME_CHAIN_SOURCE, "event_count": len(events), "events": events, "module_summary": module_summary})
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["path"] = str(path)
    return payload


def _wrap_runtime_apply_callable(module: Any, attr_name: str) -> bool:
    original = getattr(module, attr_name, None)
    if not callable(original) or getattr(original, "__autoplay_runtime_apply_chain_wrapped__", False):
        return False
    module_name = str(getattr(module, "__name__", type(module).__name__))
    key = f"{module_name}:{attr_name}"
    if key in _RUNTIME_CHAIN_WRAPPED:
        return False

    @functools.wraps(original)
    def wrapper(*args: Any, __original: Callable[..., Any] = original, __module: str = module_name, __name: str = attr_name, **kwargs: Any) -> Any:
        started = time.perf_counter()
        error: BaseException | None = None
        try:
            return __original(*args, **kwargs)
        except BaseException as exc:  # diagnostics only; preserve behavior
            error = exc
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            try:
                record_runtime_apply_chain_event(
                    module_name=__module,
                    function_name=__name,
                    elapsed_ms=elapsed_ms,
                    ok=error is None,
                    error=error,
                )
            except Exception:
                pass

    wrapper.__autoplay_runtime_apply_chain_wrapped__ = True  # type: ignore[attr-defined]
    setattr(module, attr_name, wrapper)
    _RUNTIME_CHAIN_WRAPPED.add(key)
    return True


def wrap_runtime_apply_chain() -> Dict[str, Any]:
    wrapped: List[str] = []
    module_names = ["app.rpg.session.runtime"] + [f"app.rpg.session.runtime_part{index:02d}" for index in range(1, 28)]
    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        for attr_name in ("_apply_turn_authoritative", "_base_apply_turn_authoritative", "apply_turn"):
            try:
                if _wrap_runtime_apply_callable(module, attr_name):
                    wrapped.append(f"{module_name}.{attr_name}")
            except Exception:
                continue
    return {"ok": True, "source": RUNTIME_CHAIN_SOURCE, "wrapped_count": len(wrapped), "wrapped_names": wrapped}


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
    chain = wrap_runtime_apply_chain()
    return {
        "ok": True,
        "source": SOURCE,
        "wrapped_count": len(wrapped),
        "wrapped_names": wrapped,
        "runtime_apply_chain": chain,
    }
