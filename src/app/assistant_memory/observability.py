"""Content-free aggregate observability for companion memory runtime behavior."""
from __future__ import annotations

import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_LOCK = threading.RLock()
_COUNTERS: Counter[str] = Counter()
_TOTALS: Counter[str] = Counter()
_MAXIMA: dict[str, float] = {}
_LATEST_USAGE: dict[str, "MemoryUsageResponse"] = {}
_ALLOWED_REASON_FIELDS = {
    "action",
    "reason",
    "disabled_reason",
}


class CompanionMemoryMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    turns: int = 0
    counters: dict[str, int] = Field(default_factory=dict)
    totals: dict[str, float] = Field(default_factory=dict)
    maxima: dict[str, float] = Field(default_factory=dict)
    diagnostics_policy: str = "content_free"


class MemoryUsageItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str
    selection_reason: str
    activation_score: int
    section: str
    source_revision: int = Field(ge=1)


class MemoryUsageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    recorded_at: str
    items: tuple[MemoryUsageItem, ...] = ()
    diagnostics_policy: str = "content_free"


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _count_reason(prefix: str, payload: dict[str, Any]) -> None:
    for field in _ALLOWED_REASON_FIELDS:
        value = payload.get(field)
        if isinstance(value, str) and value and len(value) <= 80:
            _COUNTERS[f"{prefix}.{field}.{value}"] += 1


def _record_section(prefix: str, payload: object) -> None:
    if not isinstance(payload, dict):
        return
    _count_reason(prefix, payload)
    for key in (
        "candidate_count",
        "selected_count",
        "excluded_count",
        "signal_count",
        "record_count",
        "token_estimate",
        "packet_tokens",
        "preload_ms",
        "rank_ms",
        "build_ms",
        "packet_build_ms",
        "deadline_ms",
    ):
        numeric = _number(payload.get(key))
        if numeric is None:
            continue
        metric = f"{prefix}.{key}"
        _TOTALS[metric] += numeric
        _MAXIMA[metric] = max(_MAXIMA.get(metric, numeric), numeric)
    for key in (
        "cache_hit",
        "preload_cache_hit",
        "preload_timed_out",
        "truncated",
        "proactive",
        "private_mode",
        "durable_candidate_created",
    ):
        value = payload.get(key)
        if isinstance(value, bool):
            _COUNTERS[f"{prefix}.{key}.{str(value).lower()}"] += 1


def record_companion_diagnostics(diagnostics: dict[str, Any]) -> None:
    """Aggregate only an allowlisted numeric/boolean/reason projection."""

    with _LOCK:
        _COUNTERS["turns"] += 1
        for section in (
            "companion_context",
            "temporal_retrieval",
            "initiative",
            "paralinguistic_state",
            "rollout",
        ):
            _record_section(section, diagnostics.get(section))


def record_memory_usage(session_id: str, items: list[dict[str, object]]) -> None:
    """Store the latest content-free selection explanation for one Chat."""

    validated = tuple(MemoryUsageItem.model_validate(item) for item in items[:50])
    with _LOCK:
        _LATEST_USAGE[session_id] = MemoryUsageResponse(
            session_id=session_id,
            recorded_at=datetime.now(timezone.utc).isoformat(),
            items=validated,
        )


def memory_usage_snapshot(session_id: str) -> MemoryUsageResponse:
    with _LOCK:
        current = _LATEST_USAGE.get(session_id)
        if current is not None:
            return current
    return MemoryUsageResponse(
        session_id=session_id,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )


def companion_metrics_snapshot() -> CompanionMemoryMetrics:
    with _LOCK:
        return CompanionMemoryMetrics(
            turns=int(_COUNTERS.get("turns", 0)),
            counters={
                key: int(value)
                for key, value in sorted(_COUNTERS.items())
                if key != "turns"
            },
            totals={key: round(float(value), 3) for key, value in sorted(_TOTALS.items())},
            maxima={key: round(float(value), 3) for key, value in sorted(_MAXIMA.items())},
        )


def reset_companion_metrics() -> None:
    with _LOCK:
        _COUNTERS.clear()
        _TOTALS.clear()
        _MAXIMA.clear()
        _LATEST_USAGE.clear()


__all__ = [
    "CompanionMemoryMetrics",
    "MemoryUsageItem",
    "MemoryUsageResponse",
    "companion_metrics_snapshot",
    "memory_usage_snapshot",
    "record_companion_diagnostics",
    "record_memory_usage",
    "reset_companion_metrics",
]
