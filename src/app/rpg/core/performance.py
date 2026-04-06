"""Phase 21 — Performance / scaling / orchestration polish.

Profiling, hot-path optimization, partial recompute, batching,
streaming latency, memory compaction, large-world scaling,
stress testing, performance stability.

IMPORTANT:
This module is strictly diagnostic. Wall-clock timing and benchmark
measurements must never be used as authoritative simulation inputs.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

def _sf(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

def _si(v: Any, d: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return d

def _ss(v: Any, d: str = "") -> str:
    return str(v) if v is not None else d


def _normalize_unit(v: Any) -> str:
    unit = _ss(v, "ms")
    return unit if unit in VALID_METRIC_UNITS else "ms"

# Constants
MAX_METRICS = 1000
MAX_BATCH_SIZE = 50
MAX_PROFILE_ENTRIES = 500
VALID_METRIC_UNITS = {"ms", "count", "bytes"}

# ---------------------------------------------------------------------------
# 21.0 — Profiling / metrics foundations
# ---------------------------------------------------------------------------

@dataclass
class PerformanceMetric:
    name: str = ""
    value: float = 0.0
    unit: str = "ms"
    tick: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "tick": self.tick,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerformanceMetric":
        return cls(
            name=_ss(d.get("name")),
            value=max(0.0, _sf(d.get("value"))),
            unit=_normalize_unit(d.get("unit")),
            tick=max(0, _si(d.get("tick"))),
        )


@dataclass
class PerformanceState:
    metrics: List[PerformanceMetric] = field(default_factory=list)
    tick: int = 0
    budget_ms: float = 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metrics": [m.to_dict() for m in self.metrics],
            "tick": self.tick, "budget_ms": self.budget_ms,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerformanceState":
        return cls(
            metrics=[PerformanceMetric.from_dict(m) for m in (d.get("metrics") or [])],
            tick=_si(d.get("tick")),
            budget_ms=_sf(d.get("budget_ms"), 100.0),
        )

    def record(self, name: str, value: float, unit: str = "ms") -> None:
        self.metrics.append(PerformanceMetric(
            name=_ss(name),
            value=max(0.0, _sf(value)),
            unit=_normalize_unit(unit),
            tick=max(0, self.tick),
        ))
        if len(self.metrics) > MAX_METRICS:
            self.metrics = self.metrics[-MAX_METRICS:]

    def record_diagnostic_only(self, name: str, value: float, unit: str = "ms") -> None:
        """Alias that makes the intended usage explicit."""
        self.record(name=name, value=value, unit=unit)


# ---------------------------------------------------------------------------
# 21.1 — Hot-path optimization
# ---------------------------------------------------------------------------

class HotPathOptimizer:
    """Identify and report hot paths."""

    @staticmethod
    def identify_hot_paths(state: PerformanceState,
                           threshold_ms: float = 10.0) -> List[Dict[str, Any]]:
        totals: Dict[str, float] = {}
        counts: Dict[str, int] = {}
        for m in state.metrics:
            if m.unit == "ms":
                totals[m.name] = totals.get(m.name, 0.0) + m.value
                counts[m.name] = counts.get(m.name, 0) + 1
        hot: List[Dict[str, Any]] = []
        for name, total in totals.items():
            avg = total / counts[name] if counts[name] > 0 else 0
            if avg > threshold_ms:
                hot.append({"name": name, "avg_ms": round(avg, 2),
                            "total_ms": round(total, 2), "count": counts[name]})
        hot.sort(key=lambda h: h["avg_ms"], reverse=True)
        return hot


# ---------------------------------------------------------------------------
# 21.2 — Partial recompute / incremental builders
# ---------------------------------------------------------------------------

class IncrementalBuilder:
    """Track which subsystems need recomputation."""

    def __init__(self) -> None:
        self.dirty_flags: Dict[str, bool] = {}

    def mark_dirty(self, subsystem: str) -> None:
        self.dirty_flags[subsystem] = True

    def mark_clean(self, subsystem: str) -> None:
        self.dirty_flags[subsystem] = False

    def get_dirty(self) -> List[str]:
        return sorted(k for k, v in self.dirty_flags.items() if v)

    def is_dirty(self, subsystem: str) -> bool:
        return self.dirty_flags.get(subsystem, False)

    def to_dict(self) -> Dict[str, Any]:
        return {"dirty_flags": dict(self.dirty_flags)}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IncrementalBuilder":
        ib = cls()
        ib.dirty_flags = dict(d.get("dirty_flags") or {})
        return ib


# ---------------------------------------------------------------------------
# 21.3 — Runtime/orchestration batching
# ---------------------------------------------------------------------------

class BatchProcessor:
    """Batch operations for efficiency."""

    @staticmethod
    def batch_events(events: List[Dict[str, Any]],
                     batch_size: int = MAX_BATCH_SIZE) -> List[List[Dict[str, Any]]]:
        batches: List[List[Dict[str, Any]]] = []
        for i in range(0, len(events), batch_size):
            batches.append(events[i:i + batch_size])
        return batches

    @staticmethod
    def merge_redundant_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: Dict[str, Dict[str, Any]] = {}
        for evt in events:
            key = f"{evt.get('type')}:{evt.get('target_id', '')}:{evt.get('actor_id', '')}"
            if key in seen:
                seen[key]["count"] = seen[key].get("count", 1) + 1
            else:
                seen[key] = dict(evt)
                seen[key]["count"] = 1
        return list(seen.values())


# ---------------------------------------------------------------------------
# 21.4 — Streaming latency reduction
# ---------------------------------------------------------------------------

class StreamingOptimizer:
    """Optimize streaming response latency."""

    @staticmethod
    def chunk_response(text: str, chunk_size: int = 100) -> List[str]:
        chunks: List[str] = []
        for i in range(0, len(text), chunk_size):
            chunks.append(text[i:i + chunk_size])
        return chunks

    @staticmethod
    def estimate_token_count(text: str) -> int:
        return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# 21.5 — Memory / state compaction
# ---------------------------------------------------------------------------

class StateCompactor:
    """Compact state to reduce memory footprint."""

    @staticmethod
    def compact_history(history: List[Dict[str, Any]],
                        max_entries: int = 100) -> List[Dict[str, Any]]:
        if len(history) <= max_entries:
            return list(history)
        return history[-max_entries:]

    @staticmethod
    def compact_metrics(metrics: List[PerformanceMetric],
                        max_entries: int = MAX_METRICS) -> List[PerformanceMetric]:
        if len(metrics) <= max_entries:
            return list(metrics)
        return metrics[-max_entries:]

    @staticmethod
    def estimate_state_size(state: Dict[str, Any]) -> int:
        """Estimate size in bytes."""
        return len(str(state))


# ---------------------------------------------------------------------------
# 21.6 — Large-world scaling rules
# ---------------------------------------------------------------------------

class ScalingRules:
    """Rules for scaling with world size."""

    THRESHOLDS = {
        "small": {"max_npcs": 20, "max_locations": 10, "tick_budget_ms": 50},
        "medium": {"max_npcs": 50, "max_locations": 30, "tick_budget_ms": 100},
        "large": {"max_npcs": 100, "max_locations": 60, "tick_budget_ms": 200},
    }

    @classmethod
    def get_scale(cls, npc_count: int, location_count: int) -> str:
        if npc_count <= 20 and location_count <= 10:
            return "small"
        elif npc_count <= 50 and location_count <= 30:
            return "medium"
        return "large"

    @classmethod
    def get_thresholds(cls, scale: str) -> Dict[str, int]:
        return dict(cls.THRESHOLDS.get(scale, cls.THRESHOLDS["medium"]))


# ---------------------------------------------------------------------------
# 21.7 — Stress testing / benchmark harness
# ---------------------------------------------------------------------------

class BenchmarkHarness:
    """Simple benchmark for measuring subsystem performance."""

    @staticmethod
    def benchmark(func: Callable, iterations: int = 100) -> Dict[str, Any]:
        times: List[float] = []
        for _ in range(iterations):
            start = time.monotonic()
            func()
            elapsed = (time.monotonic() - start) * 1000  # ms
            times.append(elapsed)
        return {
            "iterations": iterations,
            "avg_ms": round(sum(times) / len(times), 3) if times else 0,
            "min_ms": round(min(times), 3) if times else 0,
            "max_ms": round(max(times), 3) if times else 0,
            "total_ms": round(sum(times), 3),
            "diagnostic_only": True,
        }


# ---------------------------------------------------------------------------
# 21.8 — Performance stability fix pass
# ---------------------------------------------------------------------------

class PerformanceDeterminismValidator:
    @staticmethod
    def validate_bounds(state: PerformanceState) -> List[str]:
        violations: List[str] = []
        if len(state.metrics) > MAX_METRICS:
            violations.append(f"metrics exceed max ({len(state.metrics)} > {MAX_METRICS})")
        for metric in state.metrics:
            if metric.value < 0.0:
                violations.append(f"metric {metric.name} has negative value: {metric.value}")
            if metric.tick < 0:
                violations.append(f"metric {metric.name} has negative tick: {metric.tick}")
            if metric.unit not in VALID_METRIC_UNITS:
                violations.append(f"metric {metric.name} has invalid unit: {metric.unit}")
        return violations

    @staticmethod
    def validate_diagnostic_only_payload(payload: Dict[str, Any]) -> List[str]:
        violations: List[str] = []
        if "diagnostic_only" in payload and payload.get("diagnostic_only") is not True:
            violations.append("benchmark payload diagnostic_only flag must be True")
        return violations

    @staticmethod
    def normalize_state(state: PerformanceState) -> PerformanceState:
        metrics = [PerformanceMetric.from_dict(m.to_dict()) for m in state.metrics]
        if len(metrics) > MAX_METRICS:
            metrics = metrics[-MAX_METRICS:]
        metrics = sorted(
            metrics,
            key=lambda m: (m.tick, m.name, m.unit, m.value),
        )
        return PerformanceState(
            metrics=metrics,
            tick=max(0, state.tick),
            budget_ms=max(0.0, state.budget_ms),
        )
