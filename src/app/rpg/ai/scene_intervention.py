"""Deterministic player intervention in active scenes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v) if not isinstance(v, str) else v


_VALID_INTERVENTIONS = {
    "observe_scene",
    "step_into_scene",
    "ask_about_scene",
    "support_primary",
    "support_secondary",
    "calm_scene",
    "provoke_scene",
    "redirect_scene",
    "leave_scene",
}


def get_active_scene(runtime_state: Dict[str, Any], scene_id: str) -> Optional[Dict[str, Any]]:
    runtime_state = _safe_dict(runtime_state)
    scene_runtime = _safe_dict(runtime_state.get("scene_runtime"))
    for scene in _safe_list(scene_runtime.get("active_scenes")):
        scene = _safe_dict(scene)
        if _safe_str(scene.get("scene_id")) == _safe_str(scene_id):
            return scene
    return None


def validate_scene_intervention(
    runtime_state: Dict[str, Any],
    simulation_state: Dict[str, Any],
    scene_id: str,
    action_type: str,
) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    simulation_state = _safe_dict(simulation_state)
    action_type = _safe_str(action_type)

    if action_type not in _VALID_INTERVENTIONS:
        return {"ok": False, "error": "invalid_scene_intervention"}

    scene = get_active_scene(runtime_state, scene_id)
    if not scene:
        return {"ok": False, "error": "scene_not_found"}

    if _safe_str(scene.get("status")) != "active":
        return {"ok": False, "error": "scene_not_active"}

    player_state = _safe_dict(simulation_state.get("player_state"))
    player_loc = _safe_str(player_state.get("location_id"))
    if _safe_str(scene.get("location_id")) != player_loc:
        return {"ok": False, "error": "scene_not_nearby"}

    return {"ok": True, "scene": scene}


def apply_scene_intervention(
    runtime_state: Dict[str, Any],
    simulation_state: Dict[str, Any],
    *,
    scene_id: str,
    action_type: str,
) -> Dict[str, Any]:
    runtime_state = dict(_safe_dict(runtime_state))
    simulation_state = _safe_dict(simulation_state)
    scene_runtime = dict(_safe_dict(runtime_state.get("scene_runtime")))
    active_scenes = []
    result = {
        "ok": True,
        "scene_id": scene_id,
        "action_type": action_type,
        "beats": [],
        "resolved": False,
        "tension_delta": 0.0,
    }

    for scene in _safe_list(scene_runtime.get("active_scenes")):
        scene = dict(_safe_dict(scene))
        if _safe_str(scene.get("scene_id")) != _safe_str(scene_id):
            active_scenes.append(scene)
            continue

        tension = float(scene.get("tension", 0.0) or 0.0)
        primary = _safe_str(scene.get("primary_speaker_id"))
        secondary = _safe_str(scene.get("secondary_speaker_id"))
        topic = _safe_str(scene.get("topic"))
        location_id = _safe_str(scene.get("location_id"))
        beat_cursor = int(scene.get("beat_cursor", 0) or 0)

        if action_type == "observe_scene":
            result["beats"] = [{
                "kind": "npc_to_player",
                "speaker_id": secondary or primary,
                "target_id": "player",
                "text_hint": "You pause and listen more closely as the exchange unfolds.",
                "reason": "scene_observation",
                "priority": 0.35,
                "location_id": location_id,
                "scene_id": scene_id,
                "scene_kind": _safe_str(scene.get("scene_kind")),
                "beat_index": beat_cursor + 100,
            }]

        elif action_type == "step_into_scene":
            scene["player_pull"] = "address_player"
            tension = min(1.0, tension + 0.04)
            result["tension_delta"] = 0.04
            result["beats"] = [{
                "kind": "npc_to_player",
                "speaker_id": primary or secondary,
                "target_id": "player",
                "text_hint": "Both of them turn toward you as you step into the exchange.",
                "reason": "scene_step_in",
                "priority": 0.55,
                "location_id": location_id,
                "scene_id": scene_id,
                "scene_kind": _safe_str(scene.get("scene_kind")),
                "beat_index": beat_cursor + 100,
            }]

        elif action_type == "ask_about_scene":
            scene["player_pull"] = "address_player"
            result["beats"] = [{
                "kind": "npc_to_player",
                "speaker_id": secondary or primary,
                "target_id": "player",
                "text_hint": "You ask what is going on, and the argument shifts toward explanation.",
                "reason": f"{topic}_player_question",
                "priority": 0.52,
                "location_id": location_id,
                "scene_id": scene_id,
                "scene_kind": _safe_str(scene.get("scene_kind")),
                "beat_index": beat_cursor + 100,
            }]

        elif action_type == "support_primary":
            tension = min(1.0, tension + 0.08)
            result["tension_delta"] = 0.08
            result["beats"] = [{
                "kind": "npc_to_player",
                "speaker_id": primary,
                "target_id": "player",
                "text_hint": "You back their position, and the scene sharpens immediately.",
                "reason": "scene_support_primary",
                "priority": 0.58,
                "location_id": location_id,
                "scene_id": scene_id,
                "scene_kind": _safe_str(scene.get("scene_kind")),
                "beat_index": beat_cursor + 100,
            }]

        elif action_type == "support_secondary":
            tension = min(1.0, tension + 0.08)
            result["tension_delta"] = 0.08
            result["beats"] = [{
                "kind": "npc_to_player",
                "speaker_id": secondary,
                "target_id": "player",
                "text_hint": "You take their side, and the disagreement turns harder.",
                "reason": "scene_support_secondary",
                "priority": 0.58,
                "location_id": location_id,
                "scene_id": scene_id,
                "scene_kind": _safe_str(scene.get("scene_kind")),
                "beat_index": beat_cursor + 100,
            }]

        elif action_type == "calm_scene":
            tension = max(0.0, tension - 0.15)
            result["tension_delta"] = -0.15
            result["beats"] = [{
                "kind": "npc_to_player",
                "speaker_id": primary or secondary,
                "target_id": "player",
                "text_hint": "You try to calm them, and the edge in the scene softens slightly.",
                "reason": "scene_calm_attempt",
                "priority": 0.5,
                "location_id": location_id,
                "scene_id": scene_id,
                "scene_kind": _safe_str(scene.get("scene_kind")),
                "beat_index": beat_cursor + 100,
            }]
            if tension <= 0.2:
                scene["status"] = "resolved"
                result["resolved"] = True

        elif action_type == "provoke_scene":
            tension = min(1.0, tension + 0.18)
            result["tension_delta"] = 0.18
            result["beats"] = [{
                "kind": "npc_to_player",
                "speaker_id": secondary or primary,
                "target_id": "player",
                "text_hint": "Your words make the scene worse almost immediately.",
                "reason": "scene_provoked",
                "priority": 0.7,
                "location_id": location_id,
                "scene_id": scene_id,
                "scene_kind": _safe_str(scene.get("scene_kind")),
                "beat_index": beat_cursor + 100,
            }]

        elif action_type == "redirect_scene":
            scene["topic"] = "player_intervention"
            tension = max(0.0, tension - 0.05)
            result["tension_delta"] = -0.05
            result["beats"] = [{
                "kind": "npc_to_player",
                "speaker_id": primary or secondary,
                "target_id": "player",
                "text_hint": "You redirect the exchange, forcing both of them to respond to you instead.",
                "reason": "scene_redirected",
                "priority": 0.54,
                "location_id": location_id,
                "scene_id": scene_id,
                "scene_kind": _safe_str(scene.get("scene_kind")),
                "beat_index": beat_cursor + 100,
            }]

        elif action_type == "leave_scene":
            result["beats"] = [{
                "kind": "world_event",
                "speaker_id": "",
                "target_id": "",
                "text_hint": "You step away, leaving the scene to continue without you.",
                "reason": "scene_left",
                "priority": 0.32,
                "location_id": location_id,
                "scene_id": scene_id,
                "scene_kind": _safe_str(scene.get("scene_kind")),
                "beat_index": beat_cursor + 100,
            }]

        scene["tension"] = tension
        scene["player_intervened_tick"] = beat_cursor + 1
        active_scenes.append(scene)

    scene_runtime["active_scenes"] = active_scenes
    runtime_state["scene_runtime"] = scene_runtime
    result["runtime_state"] = runtime_state
    return result