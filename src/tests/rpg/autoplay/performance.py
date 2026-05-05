from __future__ import annotations

import statistics
import time
from contextlib import contextmanager
from typing import Any, Dict, List, TypedDict


class SlowTurn(TypedDict):
    turn_index: Any
    player_action: Any
    turn_total_ms: float
    player_agent_ms: float
    manual_turn_ms: float
    story_hooks_ms: float
    base_response_ms: float
    checkpoint_ms: float


def _make_slow_turn(row: Dict[str, Any]) -> SlowTurn:
    perf = row.get("performance") or {}
    return {
        "turn_index": row.get("turn_index"),
        "player_action": row.get("player_action"),
        "turn_total_ms": _safe_float(perf.get("turn_total_ms")),
        "player_agent_ms": _safe_float(perf.get("player_agent_ms")),
        "manual_turn_ms": _safe_float(perf.get("manual_turn_ms")),
        "story_hooks_ms": _safe_float(perf.get("story_hooks_ms")),
        "base_response_ms": _safe_float(perf.get("base_response_ms")),
        "checkpoint_ms": _safe_float(perf.get("checkpoint_ms")),
    }


def now_perf() -> float:
    return time.perf_counter()


def elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)


@contextmanager
def timed_stage(target: Dict[str, Any], key: str):
    start = now_perf()
    try:
        yield
    finally:
        target[key] = elapsed_ms(start)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return round(values[0], 3)
    index = (len(values) - 1) * percentile
    low = int(index)
    high = min(low + 1, len(values) - 1)
    fraction = index - low
    return round(values[low] + (values[high] - values[low]) * fraction, 3)


def summarize_performance(
    *,
    transcript: List[Dict[str, Any]],
    campaign_wall_ms: float,
    artifact_write_ms: float = 0.0,
) -> Dict[str, Any]:
    turn_timings = [
        row.get("performance") or {}
        for row in transcript
        if isinstance(row.get("performance"), dict)
    ]
    total_turn_ms = [
        _safe_float(row.get("turn_total_ms"))
        for row in turn_timings
        if _safe_float(row.get("turn_total_ms")) > 0
    ]

    def stage_values(stage: str) -> List[float]:
        return [
            _safe_float(row.get(stage))
            for row in turn_timings
            if _safe_float(row.get(stage)) > 0
        ]

    stage_keys = [
        "player_agent_ms",
        "manual_turn_ms",
        "story_hooks_ms",
        "base_response_ms",
        "progress_eval_ms",
        "state_bounds_ms",
        "record_build_ms",
        "playable_blocking_ms",
        "human_playable_blocking_ms",
        "background_enqueue_ms",
    ]
    stage_summary = {}
    for key in stage_keys:
        values = stage_values(key)
        stage_summary[key] = {
            "total_ms": round(sum(values), 3),
            "avg_ms": round(statistics.mean(values), 3) if values else 0.0,
            "max_ms": round(max(values), 3) if values else 0.0,
            "count": len(values),
        }

    slowest_turns: List[SlowTurn] = sorted(
        [_make_slow_turn(row) for row in transcript],
        key=lambda row: row["turn_total_ms"],
        reverse=True,
    )[:10]

    turn_count = len(transcript)
    campaign_seconds = campaign_wall_ms / 1000.0 if campaign_wall_ms else 0.0
    playable_blocking_ms = [
        _safe_float(row.get("playable_blocking_ms"))
        for row in turn_timings
        if _safe_float(row.get("playable_blocking_ms")) > 0
    ]
    human_playable_blocking_ms = [
        _safe_float(row.get("human_playable_blocking_ms"))
        for row in turn_timings
        if _safe_float(row.get("human_playable_blocking_ms")) > 0
    ]

    return {
        "turn_count": turn_count,
        "campaign_wall_ms": round(campaign_wall_ms, 3),
        "campaign_wall_seconds": round(campaign_seconds, 3),
        "artifact_write_ms": round(artifact_write_ms, 3),
        "turns_per_second": round(turn_count / campaign_seconds, 4) if campaign_seconds else 0.0,
        "avg_turn_ms": round(statistics.mean(total_turn_ms), 3) if total_turn_ms else 0.0,
        "avg_playable_blocking_ms": round(statistics.mean(playable_blocking_ms), 3) if playable_blocking_ms else 0.0,
        "p95_playable_blocking_ms": _percentile(playable_blocking_ms, 0.95),
        "max_playable_blocking_ms": round(max(playable_blocking_ms), 3) if playable_blocking_ms else 0.0,
        "avg_human_playable_blocking_ms": round(statistics.mean(human_playable_blocking_ms), 3) if human_playable_blocking_ms else 0.0,
        "p95_human_playable_blocking_ms": _percentile(human_playable_blocking_ms, 0.95),
        "max_human_playable_blocking_ms": round(max(human_playable_blocking_ms), 3) if human_playable_blocking_ms else 0.0,
        "median_turn_ms": round(statistics.median(total_turn_ms), 3) if total_turn_ms else 0.0,
        "p90_turn_ms": _percentile(total_turn_ms, 0.90),
        "p95_turn_ms": _percentile(total_turn_ms, 0.95),
        "max_turn_ms": round(max(total_turn_ms), 3) if total_turn_ms else 0.0,
        "min_turn_ms": round(min(total_turn_ms), 3) if total_turn_ms else 0.0,
        "stage_summary": stage_summary,
        "slowest_turns": slowest_turns,
    }