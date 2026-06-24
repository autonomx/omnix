"""Sequential scene trace helpers for RPG report rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

TRACE_SOURCE = "phase36_env_scene_trace_v1"


def carry(row: Mapping[str, object], prior: Mapping[str, object]) -> dict[str, object]:
    result = dict(row)
    turn = dict(result.get("turn_result") if isinstance(result.get("turn_result"), Mapping) else result)
    had_prior = bool(_mapping(turn.get("previous_scene")) or _mapping(turn.get("previous_environment")))
    if prior and not had_prior:
        turn["previous_scene"] = dict(prior)
    turn["env_scene_trace"] = {"source": TRACE_SOURCE, "prior_available": bool(prior), "prior_carried": bool(prior and not had_prior)}
    result["turn_result"] = turn
    result["env_scene_trace"] = turn["env_scene_trace"]
    return result


def latest(rows: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    for row in reversed(tuple(rows)):
        surface = _mapping(row.get("report_surface"))
        sections = _mapping(surface.get("sections"))
        narration = _mapping(row.get("environmental_narration")) or _mapping(sections.get("environmental_narration"))
        state = _mapping(narration.get("state_memory"))
        snapshot = _mapping(state.get("current_snapshot"))
        if snapshot:
            return snapshot
    return {}


def attach(summary: Mapping[str, object]) -> dict[str, object]:
    result = dict(summary)
    rows: list[dict[str, object]] = []
    carried = 0
    for raw in _sequence(summary.get("transcript_rows")):
        if isinstance(raw, Mapping):
            row = carry(raw, latest(rows))
            carried += int(bool(_mapping(row.get("env_scene_trace")).get("prior_carried")))
            rows.append(row)
    result["transcript_rows"] = rows
    result["env_scene_trace"] = {"source": TRACE_SOURCE, "turn_count": len(rows), "carried_count": carried}
    return result


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()
