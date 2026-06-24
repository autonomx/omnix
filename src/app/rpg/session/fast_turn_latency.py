from __future__ import annotations

from time import perf_counter
from typing import Any, Mapping

FAST_TURN_LATENCY_VERSION = "fast_turn_latency_v1"

LATENCY_STAGE_KEYS = (
    "parse_ms",
    "sim_ms",
    "context_ms",
    "retrieval_ms",
    "llm_queue_ms",
    "first_token_ms",
    "llm_total_ms",
    "postprocess_ms",
    "background_ms",
)

LATENCY_VALUE_KEYS = (
    "input_tokens",
    "output_tokens",
    "model_name",
    "mode",
)

_MANUAL_STAGE_ALIASES = {
    "pre_runtime_intent_llm_ms": "parse_ms",
    "deterministic_runtime_apply_ms": "sim_ms",
    "state_snapshot_ms": "context_ms",
    "grounding_validation_ms": "postprocess_ms",
    "repair_ms": "postprocess_ms",
    "deferred_enqueue_ms": "background_ms",
}


def latency_timer() -> float:
    """Return a monotonic timestamp for turn latency measurements."""

    return perf_counter()


def elapsed_ms(start: float) -> float:
    """Return elapsed milliseconds from a ``latency_timer`` timestamp."""

    return round((perf_counter() - start) * 1000.0, 3)


def empty_latency_record(*, mode: str = "unknown", model_name: str | None = None) -> dict[str, Any]:
    """Build the stable turn-latency payload consumed by reports and UI."""

    record: dict[str, Any] = {
        "format_version": FAST_TURN_LATENCY_VERSION,
        "mode": mode,
        "model_name": model_name,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    for key in LATENCY_STAGE_KEYS:
        record[key] = 0.0
    return record


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return round(float(value), 3)
    try:
        return round(float(str(value)), 3)
    except Exception:
        return 0.0


def merge_latency_records(*records: Mapping[str, Any] | None, mode: str = "unknown") -> dict[str, Any]:
    """Merge partial latency records without dropping the canonical schema."""

    merged = empty_latency_record(mode=mode)
    for record in records:
        if not isinstance(record, Mapping):
            continue
        merged["mode"] = str(record.get("mode") or merged.get("mode") or mode)
        model = record.get("model_name")
        if model:
            merged["model_name"] = str(model)
        for key in LATENCY_STAGE_KEYS:
            merged[key] = round(float(merged.get(key, 0.0)) + _number(record.get(key)), 3)
        for key in ("input_tokens", "output_tokens"):
            merged[key] = int(merged.get(key, 0) or 0) + int(_number(record.get(key)))
    return merged


def latency_from_manual_timing(
    manual_timing: Mapping[str, Any] | None,
    *,
    mode: str = "interactive",
    model_name: str | None = None,
) -> dict[str, Any]:
    """Translate legacy manual stage timing into the fast-turn latency schema."""

    record = empty_latency_record(mode=mode, model_name=model_name)
    if not isinstance(manual_timing, Mapping):
        return record
    for source_key, target_key in _MANUAL_STAGE_ALIASES.items():
        value = _number(manual_timing.get(source_key))
        if value:
            record[target_key] = round(float(record.get(target_key, 0.0)) + value, 3)
    total = _number(manual_timing.get("manual_turn_ms"))
    if total:
        known = sum(float(record.get(key, 0.0)) for key in LATENCY_STAGE_KEYS if key != "llm_total_ms")
        remainder = round(max(0.0, total - known), 3)
        if remainder:
            record["llm_total_ms"] = remainder
    return record


def attach_turn_latency(
    result: dict[str, Any],
    latency: Mapping[str, Any],
    *,
    key: str = "fast_turn_latency",
) -> dict[str, Any]:
    """Attach latency to a runtime result and its nested result payload."""

    if not isinstance(result, dict):
        return result
    payload = merge_latency_records(latency, mode=str(latency.get("mode") or "unknown") if isinstance(latency, Mapping) else "unknown")
    result[key] = dict(payload)
    nested = result.get("result")
    if isinstance(nested, dict):
        nested[key] = dict(payload)
        result["result"] = nested
    return result


def ensure_turn_latency(result: dict[str, Any], *, mode: str = "interactive") -> dict[str, Any]:
    """Attach latency when a result already has legacy manual timing."""

    if not isinstance(result, dict):
        return result
    existing = result.get("fast_turn_latency")
    if isinstance(existing, Mapping):
        return result
    manual = result.get("manual_turn_stage_timing")
    if not isinstance(manual, Mapping) and isinstance(result.get("result"), dict):
        manual = result["result"].get("manual_turn_stage_timing")
    return attach_turn_latency(result, latency_from_manual_timing(manual, mode=mode))
