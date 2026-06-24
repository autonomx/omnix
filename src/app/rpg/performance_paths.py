"""Performance path classification helpers for RPG turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

PathClass = Literal["must_block", "can_stream", "can_defer", "can_batch", "can_cache", "can_skip"]

FAST_ACTIONS: tuple[str, ...] = (
    "look",
    "inventory",
    "stats",
    "map",
    "journal",
    "known_travel",
    "known_purchase",
    "known_room_rental",
)

DEFAULT_PATHS: Mapping[str, PathClass] = {
    "intent_classification": "must_block",
    "simulation_resolution": "must_block",
    "grounded_response": "must_block",
    "streaming_narration": "can_stream",
    "memory_summary": "can_defer",
    "journal_recap": "can_defer",
    "visual_prompt": "can_defer",
    "offscreen_events": "can_batch",
    "soft_audit": "can_defer",
    "repeat_known_state": "can_cache",
}


@dataclass(frozen=True)
class PathDecision:
    task: str
    path_class: PathClass
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {"task": self.task, "path_class": self.path_class, "reason": self.reason}


@dataclass(frozen=True)
class LatencySample:
    task: str
    latency_ms: float
    path_class: PathClass

    def as_dict(self) -> dict[str, object]:
        return {"task": self.task, "latency_ms": self.latency_ms, "path_class": self.path_class}


def classify_turn_task(task: str, *, overrides: Mapping[str, PathClass] | None = None) -> PathDecision:
    paths = dict(DEFAULT_PATHS)
    paths.update(overrides or {})
    path_class = paths.get(task, "must_block")
    reason = "configured" if task in paths else "unknown_tasks_block"
    return PathDecision(task, path_class, reason)


def is_fast_deterministic_action(action_kind: str) -> bool:
    return action_kind in FAST_ACTIONS


def blocking_tasks(decisions: Sequence[PathDecision]) -> tuple[str, ...]:
    return tuple(decision.task for decision in decisions if decision.path_class == "must_block")


def deferred_tasks(decisions: Sequence[PathDecision]) -> tuple[str, ...]:
    return tuple(decision.task for decision in decisions if decision.path_class in ("can_defer", "can_batch"))


def performance_report(samples: Sequence[LatencySample]) -> dict[str, object]:
    total = sum(sample.latency_ms for sample in samples)
    by_class: dict[str, float] = {}
    for sample in samples:
        by_class[sample.path_class] = by_class.get(sample.path_class, 0.0) + sample.latency_ms
    return {
        "sample_count": len(samples),
        "total_latency_ms": total,
        "blocking_latency_ms": by_class.get("must_block", 0.0),
        "latency_by_class": by_class,
        "samples": [sample.as_dict() for sample in samples],
    }


def fast_action_response(action_kind: str) -> dict[str, object]:
    return {
        "action_kind": action_kind,
        "fast_path": is_fast_deterministic_action(action_kind),
        "requires_heavy_llm": not is_fast_deterministic_action(action_kind),
    }
