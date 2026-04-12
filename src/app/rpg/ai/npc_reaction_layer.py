from __future__ import annotations

from typing import Any, Dict, List
import hashlib
import json


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    if value is None:
        return default
    try:
        return bool(value)
    except Exception:
        return default


def _stable_hash(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _npc_role(npc: Dict[str, Any]) -> str:
    npc = _safe_dict(npc)
    role = _safe_str(npc.get("role")).strip().lower()
    name = _safe_str(npc.get("name")).strip().lower()
    if "guard" in role or "captain" in role or "watch" in role:
        return "guard"
    if "innkeeper" in role or "owner" in role:
        return "innkeeper"
    if "merchant" in role or "civilian" in role or "patron" in role:
        return "civilian"
    if "guard" in name or "captain" in name:
        return "guard"
    if "innkeeper" in name:
        return "innkeeper"
    return "civilian"


def build_interaction_reaction_context(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    interaction: Dict[str, Any],
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    interaction = _safe_dict(interaction)
    state = _safe_dict(interaction.get("state"))

    action_type = _safe_str(interaction.get("action_type")).strip().lower()
    subtype = _safe_str(interaction.get("subtype")).strip().lower()
    visibility = _safe_str(state.get("visibility")).strip().lower() or "local"
    intensity = max(0, min(5, _safe_int(state.get("intensity"), 1)))
    stakes = max(0, min(5, _safe_int(state.get("stakes"), 1)))

    severity = 1
    lawfulness_risk = 0
    spectacle_value = 0
    fear_value = 0
    interaction_class = "generic"

    if action_type in {"social_competition"}:
        interaction_class = "competition"
        severity = 1 + min(1, intensity)
        spectacle_value = 3
        fear_value = 0
        lawfulness_risk = 0
    elif action_type in {"social_performance"}:
        interaction_class = "performance"
        severity = 1
        spectacle_value = 3
        fear_value = 0
        lawfulness_risk = 0
    elif action_type in {"threat"}:
        interaction_class = "threat"
        severity = 2 + min(2, intensity)
        spectacle_value = 1
        fear_value = 2
        lawfulness_risk = 2
    elif action_type in {"attack_unarmed", "attack_weapon", "violence", "assault"} or "punch" in subtype:
        interaction_class = "violence"
        severity = 3 + min(2, intensity)
        spectacle_value = 1
        fear_value = 3
        lawfulness_risk = 4

    signals: List[str] = []
    if visibility in {"public", "local"}:
        signals.append("crowd_attention")
    if spectacle_value >= 2:
        signals.append("spectacle")
    if lawfulness_risk >= 2:
        signals.append("authority_attention")
    if interaction_class == "violence":
        signals.append("violence")
        signals.append("public_disruption")
    elif interaction_class == "threat":
        signals.append("public_disruption")
    elif interaction_class in {"competition", "performance"}:
        signals.append("public_activity")

    return {
        "interaction_id": _safe_str(interaction.get("id")),
        "semantic_action_id": _safe_str(interaction.get("semantic_action_id")),
        "interaction_class": interaction_class,
        "action_type": action_type,
        "subtype": subtype,
        "location_id": _safe_str(interaction.get("location_id")),
        "participants": _safe_list(interaction.get("participants")),
        "visibility": visibility,
        "intensity": intensity,
        "stakes": stakes,
        "severity": severity,
        "lawfulness_risk": lawfulness_risk,
        "spectacle_value": spectacle_value,
        "fear_value": fear_value,
        "signals": signals,
        "summary": _safe_str(state.get("summary")),
        "tick": _safe_int(interaction.get("updated_tick") or interaction.get("started_tick"), 0),
    }


def build_npc_reaction_candidates(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    context = _safe_dict(context)
    npc_index = _safe_dict(simulation_state.get("npc_index"))
    location_id = _safe_str(context.get("location_id"))
    participants = set(_safe_list(context.get("participants")))
    signals = set(_safe_list(context.get("signals")))
    interaction_class = _safe_str(context.get("interaction_class"))

    candidates: List[Dict[str, Any]] = []

    for npc_id, npc_raw in sorted(npc_index.items()):
        npc = _safe_dict(npc_raw)
        if npc_id in participants:
            continue
        if _safe_str(npc.get("location_id")) != location_id:
            continue

        role = _npc_role(npc)
        reaction_type = ""
        priority = 0
        summary = ""
        pressure_topic = ""
        pressure_delta = 0

        if role == "guard":
            if "violence" in signals:
                reaction_type = "intervene"
                priority = 100
                summary = f"{_safe_str(npc.get('name'))} steps in to stop the violence."
                pressure_topic = "law_enforcement"
                pressure_delta = 2
            elif "authority_attention" in signals or "public_disruption" in signals:
                reaction_type = "warn"
                priority = 80
                summary = f"{_safe_str(npc.get('name'))} moves closer, ready to intervene."
                pressure_topic = "law_enforcement"
                pressure_delta = 1
            elif "spectacle" in signals:
                reaction_type = "observe"
                priority = 60
                summary = f"{_safe_str(npc.get('name'))} watches the scene closely."
                pressure_topic = "watchfulness"
                pressure_delta = 1

        elif role == "innkeeper":
            if interaction_class == "violence":
                reaction_type = "call_for_help"
                priority = 85
                summary = f"{_safe_str(npc.get('name'))} shouts for help as the disturbance escalates."
                pressure_topic = "tavern_tension"
                pressure_delta = 2
            elif interaction_class in {"competition", "performance"}:
                reaction_type = "observe"
                priority = 55
                summary = f"{_safe_str(npc.get('name'))} keeps a close eye on the lively scene."
                pressure_topic = "crowd_attention"
                pressure_delta = 1

        else:
            if interaction_class == "violence":
                reaction_type = "recoil"
                priority = 70
                summary = f"{_safe_str(npc.get('name'))} recoils from the sudden violence."
                pressure_topic = "crowd_anxiety"
                pressure_delta = 1
            elif interaction_class in {"competition", "performance"}:
                reaction_type = "observe"
                priority = 50
                summary = f"{_safe_str(npc.get('name'))} pauses to watch the scene unfold."
                pressure_topic = "crowd_attention"
                pressure_delta = 1

        if not reaction_type:
            continue

        reaction_seed = {
            "interaction_id": _safe_str(context.get("interaction_id")),
            "npc_id": npc_id,
            "reaction_type": reaction_type,
        }
        reaction_id = f"npc_reaction_{_stable_hash(reaction_seed)}"

        candidates.append(
            {
                "reaction_id": reaction_id,
                "interaction_id": _safe_str(context.get("interaction_id")),
                "actor_id": npc_id,
                "actor_name": _safe_str(npc.get("name")),
                "role": role,
                "reaction_type": reaction_type,
                "location_id": location_id,
                "priority": priority,
                "summary": summary,
                "pressure_topic": pressure_topic,
                "pressure_delta": pressure_delta,
                "tags": ["npc_reaction", interaction_class, reaction_type],
                "tick": _safe_int(context.get("tick"), 0),
            }
        )

    candidates.sort(key=lambda x: (-_safe_int(x.get("priority"), 0), _safe_str(x.get("actor_id"))))
    return candidates[:4]


def select_npc_reactions(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    del simulation_state, runtime_state
    candidates = _safe_list(candidates)
    return [_safe_dict(x) for x in candidates[:3]]


def apply_npc_reactions(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    reactions: List[Dict[str, Any]],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    reactions = [_safe_dict(x) for x in _safe_list(reactions)]

    recent_rows = _safe_list(runtime_state.get("recent_world_event_rows"))
    scene_beats = _safe_list(runtime_state.get("recent_scene_beats"))
    world_pressure = _safe_list(runtime_state.get("world_pressure"))
    reaction_records = _safe_list(runtime_state.get("npc_reaction_records"))
    seen_ids = {_safe_str(_safe_dict(x).get("reaction_id")) for x in reaction_records}

    row_index = {
        _safe_str(_safe_dict(x).get("event_id")): idx
        for idx, x in enumerate(recent_rows)
        if _safe_str(_safe_dict(x).get("event_id"))
    }
    beat_index = {
        _safe_str(_safe_dict(x).get("event_id")): idx
        for idx, x in enumerate(scene_beats)
        if _safe_str(_safe_dict(x).get("event_id"))
    }
    pressure_index = {
        _safe_str(_safe_dict(x).get("id")): idx
        for idx, x in enumerate(world_pressure)
        if _safe_str(_safe_dict(x).get("id"))
    }

    for reaction in reactions:
        reaction_id = _safe_str(reaction.get("reaction_id"))
        if not reaction_id:
            continue

        tick = _safe_int(reaction.get("tick"), 0)
        summary = _safe_str(reaction.get("summary"))
        actor_id = _safe_str(reaction.get("actor_id"))
        actor_name = _safe_str(reaction.get("actor_name"))
        reaction_type = _safe_str(reaction.get("reaction_type"))
        location_id = _safe_str(reaction.get("location_id"))

        row = {
            "event_id": reaction_id,
            "scope": "local",
            "kind": "npc_reaction_beat",
            "title": "NPC Reaction",
            "summary": summary,
            "tick": tick,
            "actors": [actor_id],
            "actor_id": actor_id,
            "actor_name": actor_name,
            "location_id": location_id,
            "priority": 90,
            "source": "npc_reaction_layer",
            "tags": _safe_list(reaction.get("tags")),
        }
        if reaction_id in row_index:
            recent_rows[row_index[reaction_id]] = row
        else:
            row_index[reaction_id] = len(recent_rows)
            recent_rows.append(row)

        beat_id = f"scene_beat:{reaction_id}"
        beat = {
            "event_id": beat_id,
            "kind": "npc_reaction_beat",
            "summary": summary,
            "tick": tick,
            "actor_id": actor_id,
            "location_id": location_id,
            "source": "npc_reaction_layer",
            "tags": _safe_list(reaction.get("tags")),
        }
        if beat_id in beat_index:
            scene_beats[beat_index[beat_id]] = beat
        else:
            beat_index[beat_id] = len(scene_beats)
            scene_beats.append(beat)

        pressure_topic = _safe_str(reaction.get("pressure_topic"))
        pressure_delta = _safe_int(reaction.get("pressure_delta"), 0)
        if pressure_topic and pressure_delta:
            pressure_id = f"pressure_{reaction_id}"
            pressure_row = {
                "id": pressure_id,
                "topic": pressure_topic,
                "summary": summary,
                "delta": pressure_delta,
                "tick": tick,
                "source": "npc_reaction_layer",
                "location_id": location_id,
                "actor_id": actor_id,
            }
            if pressure_id in pressure_index:
                world_pressure[pressure_index[pressure_id]] = pressure_row
            else:
                pressure_index[pressure_id] = len(world_pressure)
                world_pressure.append(pressure_row)

        if reaction_id not in seen_ids:
            reaction_records.append(
                {
                    "reaction_id": reaction_id,
                    "interaction_id": _safe_str(reaction.get("interaction_id")),
                    "actor_id": actor_id,
                    "reaction_type": reaction_type,
                    "tick": tick,
                }
            )
            seen_ids.add(reaction_id)

    runtime_state["recent_world_event_rows"] = recent_rows[-64:]
    runtime_state["recent_scene_beats"] = scene_beats[-64:]
    runtime_state["world_pressure"] = world_pressure[-32:]
    runtime_state["npc_reaction_records"] = reaction_records[-64:]
    return simulation_state, runtime_state