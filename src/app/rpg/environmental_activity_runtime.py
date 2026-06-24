"""Living scene activity helpers for RPG environmental runtime expansion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

ENVIRONMENTAL_ACTIVITY_SOURCE = "phase34_environmental_activity_runtime_v1"


def build_environmental_activity_report(turn_result: Mapping[str, object]) -> dict[str, object]:
    """Build deterministic visible-activity metadata for the current scene."""

    state = _mapping(turn_result.get("simulation_state") or turn_result.get("state"))
    world = _mapping(state.get("world"))
    location = _mapping(state.get("location") or turn_result.get("location"))
    env = _mapping(state.get("environment") or turn_result.get("environment"))
    location_id = str(turn_result.get("location_id") or location.get("location_id") or location.get("id") or "")
    visible = _visible_activity(turn_result, state, world, location, env, location_id)
    intensity = _intensity(visible)
    issues = tuple(_issues(turn_result, location, visible))
    return {
        "source": ENVIRONMENTAL_ACTIVITY_SOURCE,
        "ready": not issues,
        "issues": list(issues),
        "location": location_id,
        "time_of_day": str(env.get("time_of_day") or world.get("time_of_day") or turn_result.get("time_of_day") or ""),
        "visible_activity": visible,
        "actor_groups": _actor_groups(visible),
        "intensity": intensity,
        "opportunities": _opportunities(visible),
        "narration_guidance": _guidance(intensity, visible),
    }


def attach_environmental_activity_to_summary(summary: Mapping[str, object]) -> dict[str, object]:
    """Attach living scene activity metadata to each transcript row."""

    result = dict(summary)
    rows: list[dict[str, object]] = []
    for raw in _sequence(summary.get("transcript_rows")):
        if isinstance(raw, Mapping):
            row = dict(raw)
            row["environmental_activity"] = build_environmental_activity_report(
                _mapping(raw.get("turn_result")) or raw
            )
            rows.append(row)
    result["transcript_rows"] = rows
    result["environmental_activity"] = _aggregate(rows)
    return result


def _visible_activity(
    turn_result: Mapping[str, object],
    state: Mapping[str, object],
    world: Mapping[str, object],
    location: Mapping[str, object],
    env: Mapping[str, object],
    location_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    rows.extend(_activity_rows("population", env.get("population_activity")))
    rows.extend(_activity_rows("population", location.get("ambient_activity") or location.get("current_activity")))
    rows.extend(_activity_rows("npc", turn_result.get("nearby_npc_activity")))
    rows.extend(_scheduled_actor_rows(turn_result, state, world, location, location_id))
    rows.extend(_activity_rows("event", turn_result.get("active_events") or world.get("active_events")))
    rows.extend(_scheduled_event_rows(turn_result, state, world, location, location_id))
    rows.extend(_activity_rows("faction", world.get("faction_presence") or location.get("faction_presence")))
    rows.extend(_activity_rows("hazard", world.get("hazards") or location.get("hazards")))
    scene_activity = turn_result.get("scene_activity") or turn_result.get("action_category")
    rows.extend(_activity_rows("scene", scene_activity))
    return _dedupe(rows)


def _scheduled_actor_rows(
    turn_result: Mapping[str, object],
    state: Mapping[str, object],
    world: Mapping[str, object],
    location: Mapping[str, object],
    location_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for source in (
        turn_result.get("npc_schedules"),
        turn_result.get("npc_activity"),
        state.get("npc_schedules"),
        state.get("npcs"),
        world.get("npc_schedules"),
        world.get("npcs"),
        location.get("npcs"),
    ):
        for item in _sequence(source):
            actor = _mapping(item)
            if not actor or not _matches_location(actor, location_id):
                continue
            label = str(actor.get("name") or actor.get("npc") or actor.get("id") or "someone")
            action = str(actor.get("activity") or actor.get("action") or actor.get("status") or actor.get("task") or "is present")
            rows.append({"kind": "npc", "text": f"{label}: {action}"})
    return rows


def _scheduled_event_rows(
    turn_result: Mapping[str, object],
    state: Mapping[str, object],
    world: Mapping[str, object],
    location: Mapping[str, object],
    location_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for source in (
        turn_result.get("scheduled_events"),
        state.get("scheduled_events"),
        world.get("scheduled_events"),
        world.get("events"),
        location.get("events"),
    ):
        for item in _sequence(source):
            event = _mapping(item)
            if not event or not _matches_location(event, location_id):
                continue
            text = str(event.get("description") or event.get("summary") or event.get("name") or event.get("id") or "local event")
            rows.append({"kind": "event", "text": text})
    return rows


def _matches_location(item: Mapping[str, object], location_id: str) -> bool:
    raw = item.get("location_id") or item.get("location") or item.get("place")
    if not raw or not location_id:
        return True
    return str(raw) == location_id


def _activity_rows(kind: str, value: object) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in _text_items(value):
        rows.append({"kind": kind, "text": item})
    return rows


def _dedupe(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, object]] = []
    for row in rows:
        key = (str(row.get("kind") or ""), str(row.get("text") or ""))
        if key in seen or not key[1]:
            continue
        seen.add(key)
        result.append({"kind": key[0], "text": key[1]})
    return result


def _actor_groups(rows: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    actors = []
    for row in rows:
        kind = str(row.get("kind") or "")
        if kind in {"population", "npc", "faction"}:
            actors.append(kind)
    return tuple(dict.fromkeys(actors))


def _intensity(rows: Sequence[Mapping[str, object]]) -> str:
    kinds = {str(row.get("kind") or "") for row in rows}
    if "hazard" in kinds or "event" in kinds:
        return "high"
    if "npc" in kinds or "population" in kinds or "faction" in kinds:
        return "medium"
    if rows:
        return "low"
    return "quiet"


def _opportunities(rows: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    kinds = {str(row.get("kind") or "") for row in rows}
    opportunities = []
    if "npc" in kinds or "population" in kinds:
        opportunities.append("conversation_or_rumor")
    if "event" in kinds:
        opportunities.append("local_event_hook")
    if "faction" in kinds:
        opportunities.append("reputation_or_conflict_signal")
    if "hazard" in kinds:
        opportunities.append("danger_or_caution")
    return tuple(opportunities)


def _guidance(intensity: str, rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return "Describe the scene as calm or empty without inventing activity."
    if intensity == "high":
        return "Foreground urgent motion, hazards, or events before passive atmosphere."
    if intensity == "medium":
        return "Blend everyday motion with nearby NPC or crowd behavior."
    return "Mention the visible activity briefly as background texture."


def _issues(
    turn_result: Mapping[str, object],
    location: Mapping[str, object],
    visible: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    issues: list[str] = []
    if not (turn_result.get("location_id") or location.get("location_id") or location.get("id")):
        issues.append("missing_activity_location")
    if not visible:
        issues.append("missing_visible_activity")
    return tuple(issues)


def _aggregate(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    intensity_counts: dict[str, int] = {}
    opportunity_counts: dict[str, int] = {}
    for row in rows:
        payload = _mapping(row.get("environmental_activity"))
        intensity = str(payload.get("intensity") or "")
        if intensity:
            intensity_counts[intensity] = intensity_counts.get(intensity, 0) + 1
        for opportunity in _sequence(payload.get("opportunities")):
            key = str(opportunity)
            opportunity_counts[key] = opportunity_counts.get(key, 0) + 1
    return {
        "source": ENVIRONMENTAL_ACTIVITY_SOURCE,
        "turn_count": len(rows),
        "intensity_counts": dict(sorted(intensity_counts.items())),
        "opportunity_counts": dict(sorted(opportunity_counts.items())),
    }


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


def _text_items(value: object) -> tuple[str, ...]:
    if isinstance(value, str) and value:
        return (value,)
    return tuple(str(item) for item in _sequence(value) if str(item))
