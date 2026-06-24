"""Environmental narration trigger and scene-introduction contracts for RPG Phase 28."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

ENVIRONMENTAL_NARRATION_SOURCE = "phase28_environmental_narration_v1"
ENVIRONMENTAL_STATE_MEMORY_SOURCE = "phase33_environmental_state_memory_v1"
_TRIGGER_KEYS = (
    "new_game",
    "location_changed",
    "region_changed",
    "time_changed",
    "weather_changed",
    "major_event_changed",
    "scene_activity_changed",
    "perceived_world_changed",
    "changed_return_visit",
)
_SENSORY_KEYS = ("sights", "sounds", "smells", "physical_feel", "emotional_tone")
_CONTEXT_KEYS = (
    "region",
    "location",
    "time_of_day",
    "season",
    "weather",
    "population_activity",
    "active_events",
    "faction_presence",
    "nearby_npc_activity",
    "recent_player_actions",
    "world_consequences",
    "local_economy",
    "hazards",
    "conflicts_or_celebrations",
)
_MEMORY_KEYS = (
    "region",
    "location",
    "time_of_day",
    "season",
    "weather",
    "activity",
    "major_event",
    "emotional_tone",
    "population_activity",
    "active_events",
    "faction_presence",
    "nearby_npc_activity",
    "world_consequences",
    "hazards",
)
_PERCEPTUAL_MEMORY_KEYS = (
    "sights",
    "sounds",
    "smells",
    "physical_feel",
    "emotional_tone",
)


def build_environmental_narration_report(turn_result: Mapping[str, object]) -> dict[str, object]:
    """Build a deterministic scene-introduction contract from simulation state."""

    state = _mapping(turn_result.get("simulation_state") or turn_result.get("state"))
    previous = _previous_scene(turn_result, state)
    current = _current_scene(turn_result, state)
    memory = _state_memory(previous, current)
    triggers = _triggers(turn_result, previous, current, memory)
    contract = _scene_contract(current, triggers, memory)
    issues = tuple(_issues(triggers, contract))
    return {
        "source": ENVIRONMENTAL_NARRATION_SOURCE,
        "ready": not issues,
        "issues": list(issues),
        "should_generate": bool(triggers),
        "triggers": list(triggers),
        "scene_introduction_contract": contract,
        "state_memory": memory,
    }


def build_environmental_state_memory(turn_result: Mapping[str, object]) -> dict[str, object]:
    """Return deterministic before/after scene memory for report panels and tests."""

    state = _mapping(turn_result.get("simulation_state") or turn_result.get("state"))
    previous = _previous_scene(turn_result, state)
    current = _current_scene(turn_result, state)
    return _state_memory(previous, current)


def attach_environmental_narration_to_summary(summary: Mapping[str, object]) -> dict[str, object]:
    """Attach environmental narration contracts to summary transcript rows."""

    result = dict(summary)
    rows: list[dict[str, object]] = []
    for raw in _sequence(summary.get("transcript_rows")):
        if isinstance(raw, Mapping):
            row = dict(raw)
            row["environmental_narration"] = build_environmental_narration_report(
                _mapping(raw.get("turn_result")) or raw
            )
            rows.append(row)
    result["transcript_rows"] = rows
    result["environmental_narration"] = _aggregate(rows)
    return result


def _previous_scene(turn_result: Mapping[str, object], state: Mapping[str, object]) -> dict[str, object]:
    raw = (
        turn_result.get("previous_scene")
        or turn_result.get("previous_environment")
        or state.get("previous_scene")
        or state.get("previous_environment")
        or state.get("environmental_state_memory")
    )
    return _scene_snapshot(_mapping(raw))


def _current_scene(turn_result: Mapping[str, object], state: Mapping[str, object]) -> dict[str, object]:
    world = _mapping(state.get("world"))
    location = _mapping(state.get("location") or turn_result.get("location"))
    env = _mapping(state.get("environment") or turn_result.get("environment"))
    return _scene_snapshot(
        {
            "region": str(turn_result.get("region_id") or world.get("region_id") or location.get("region_id") or ""),
            "location": str(turn_result.get("location_id") or location.get("location_id") or location.get("id") or ""),
            "time_of_day": str(
                env.get("time_of_day") or world.get("time_of_day") or turn_result.get("time_of_day") or ""
            ),
            "season": str(env.get("season") or world.get("season") or ""),
            "weather": str(env.get("weather") or world.get("weather") or turn_result.get("weather") or ""),
            "activity": str(turn_result.get("scene_activity") or turn_result.get("action_category") or ""),
            "major_event": str(turn_result.get("major_event_id") or ""),
            "meaningful_change": bool(turn_result.get("meaningful_location_change")),
            "sights": _text_list(env.get("sights") or location.get("sights") or location.get("landmarks")),
            "sounds": _text_list(env.get("sounds") or location.get("sounds")),
            "smells": _text_list(env.get("smells") or location.get("smells")),
            "physical_feel": _text_list(env.get("physical_feel") or env.get("conditions")),
            "emotional_tone": str(env.get("emotional_tone") or world.get("tone") or ""),
            "population_activity": _text_list(env.get("population_activity")),
            "active_events": _text_list(turn_result.get("active_events") or world.get("active_events")),
            "faction_presence": _text_list(world.get("faction_presence") or location.get("faction_presence")),
            "nearby_npc_activity": _text_list(turn_result.get("nearby_npc_activity")),
            "recent_player_actions": _text_list(turn_result.get("recent_player_actions")),
            "world_consequences": _text_list(world.get("consequences") or turn_result.get("world_consequences")),
            "local_economy": str(world.get("local_economy") or location.get("local_economy") or ""),
            "hazards": _text_list(world.get("hazards") or location.get("hazards")),
            "conflicts_or_celebrations": _text_list(world.get("conflicts") or world.get("celebrations")),
        }
    )


def _scene_snapshot(scene: Mapping[str, object]) -> dict[str, object]:
    snapshot: dict[str, object] = dict(scene)
    for key in _SENSORY_KEYS + _CONTEXT_KEYS + _MEMORY_KEYS + _PERCEPTUAL_MEMORY_KEYS:
        if key not in snapshot:
            continue
        value = snapshot[key]
        if key in _PERCEPTUAL_MEMORY_KEYS or key in _CONTEXT_KEYS or key in _MEMORY_KEYS:
            snapshot[key] = _normal_memory_value(value)
    return snapshot


def _state_memory(previous: Mapping[str, object], current: Mapping[str, object]) -> dict[str, object]:
    changed: list[dict[str, object]] = []
    stable: list[str] = []
    for key in _MEMORY_KEYS:
        before = _normal_memory_value(previous.get(key))
        after = _normal_memory_value(current.get(key))
        if not before and not after:
            continue
        if before == after:
            stable.append(key)
        else:
            changed.append({"field": key, "before": before, "after": after})
    perceptual = []
    for key in _PERCEPTUAL_MEMORY_KEYS:
        before = _normal_memory_value(previous.get(key))
        after = _normal_memory_value(current.get(key))
        if before != after and (before or after):
            perceptual.append({"field": key, "before": before, "after": after})
    location_seen_before = bool(previous.get("location")) and previous.get("location") == current.get("location")
    return {
        "source": ENVIRONMENTAL_STATE_MEMORY_SOURCE,
        "location_seen_before": location_seen_before,
        "changed_fields": changed,
        "stable_fields": tuple(stable),
        "perceptual_changes": perceptual,
        "current_snapshot": {key: current.get(key) for key in _MEMORY_KEYS if current.get(key)},
    }


def _triggers(
    turn_result: Mapping[str, object],
    previous: Mapping[str, object],
    current: Mapping[str, object],
    memory: Mapping[str, object],
) -> tuple[str, ...]:
    explicit = tuple(str(item) for item in _sequence(turn_result.get("scene_intro_triggers")))
    triggers = list(explicit)
    if turn_result.get("new_game") is True:
        triggers.append("new_game")
    pairs = (
        ("location", "location_changed"),
        ("region", "region_changed"),
        ("time_of_day", "time_changed"),
        ("weather", "weather_changed"),
        ("major_event", "major_event_changed"),
        ("activity", "scene_activity_changed"),
    )
    for key, trigger in pairs:
        if previous.get(key) and previous.get(key) != current.get(key):
            triggers.append(trigger)
    if current.get("world_consequences") or current.get("hazards"):
        triggers.append("perceived_world_changed")
    has_return_change = bool(memory.get("location_seen_before")) and bool(memory.get("changed_fields"))
    if current.get("meaningful_change") and previous.get("location") == current.get("location"):
        has_return_change = True
    if has_return_change:
        triggers.append("changed_return_visit")
    return tuple(key for key in dict.fromkeys(triggers) if key in _TRIGGER_KEYS)


def _scene_contract(
    current: Mapping[str, object],
    triggers: Sequence[str],
    memory: Mapping[str, object],
) -> dict[str, object]:
    sensory = {key: current.get(key) for key in _SENSORY_KEYS}
    context = {key: current.get(key) for key in _CONTEXT_KEYS}
    return {
        "format": {
            "atmospheric_description": "1-2 paragraphs",
            "current_activity_summary": "nearby visible activity",
            "notable_observations": "landmarks, opportunities, danger, change",
            "player_awareness_cues": "perception, skills, reputation, prior knowledge",
        },
        "triggers": list(triggers),
        "sensory_inputs": sensory,
        "world_context": context,
        "state_memory": memory,
        "changed_context": list(_sequence(memory.get("changed_fields"))),
        "instructions": (
            "Establish place, atmosphere, situation, living activity, and meaningful change. "
            "Acknowledge familiarity on return visits while highlighting what changed."
        ),
    }


def _issues(triggers: Sequence[str], contract: Mapping[str, object]) -> tuple[str, ...]:
    issues: list[str] = []
    if not triggers:
        issues.append("no_scene_intro_trigger")
    sensory = _mapping(contract.get("sensory_inputs"))
    if not any(sensory.get(key) for key in _SENSORY_KEYS):
        issues.append("missing_sensory_inputs")
    context = _mapping(contract.get("world_context"))
    if not context.get("location") and not context.get("region"):
        issues.append("missing_place_context")
    return tuple(issues)


def _aggregate(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    generated = 0
    triggers: dict[str, int] = {}
    memory_change_counts: dict[str, int] = {}
    for row in rows:
        payload = _mapping(row.get("environmental_narration"))
        if payload.get("should_generate"):
            generated += 1
        for trigger in _sequence(payload.get("triggers")):
            key = str(trigger)
            triggers[key] = triggers.get(key, 0) + 1
        memory = _mapping(payload.get("state_memory"))
        for change in _sequence(memory.get("changed_fields")):
            field = str(_mapping(change).get("field") or "")
            if field:
                memory_change_counts[field] = memory_change_counts.get(field, 0) + 1
    return {
        "source": ENVIRONMENTAL_NARRATION_SOURCE,
        "turn_count": len(rows),
        "scene_intro_count": generated,
        "trigger_counts": triggers,
        "memory_change_counts": dict(sorted(memory_change_counts.items())),
    }


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


def _text_list(value: object) -> tuple[str, ...]:
    if isinstance(value, str) and value:
        return (value,)
    return tuple(str(item) for item in _sequence(value) if str(item))


def _normal_memory_value(value: object) -> object:
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(item) for item in value if str(item))
    if isinstance(value, Mapping):
        return tuple((str(key), _normal_memory_value(item)) for key, item in sorted(value.items()))
    return value if value else ""
