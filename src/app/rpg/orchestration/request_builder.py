"""Phase 10.6 — Deterministic LLM request payload builder."""
from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.runtime.dialogue_runtime import get_runtime_dialogue_state


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _safe_bool(v: Any) -> bool:
    return bool(v)


def _find_turn(dialogue_state: Dict[str, Any], turn_id: str) -> Dict[str, Any]:
    turn_id = _safe_str(turn_id)
    for item in _safe_list(dialogue_state.get("turns")):
        item = _safe_dict(item)
        if _safe_str(item.get("turn_id")) == turn_id:
            return item
    return {}


def _compact_history(dialogue_state: Dict[str, Any], limit: int = 6) -> List[Dict[str, Any]]:
    turns = [
        _safe_dict(v)
        for v in _safe_list(dialogue_state.get("turns"))
        if isinstance(v, dict)
    ]
    turns = sorted(
        turns,
        key=lambda item: (
            _safe_int(item.get("tick"), 0),
            _safe_int(item.get("sequence_index"), 0),
            _safe_str(item.get("actor_id")),
        ),
    )
    out: List[Dict[str, Any]] = []
    for item in turns[-limit:]:
        out.append({
            "turn_id": _safe_str(item.get("turn_id")),
            "actor_id": _safe_str(item.get("actor_id")),
            "speaker_id": _safe_str(item.get("speaker_id")),
            "speaker_name": _safe_str(item.get("speaker_name")),
            "role": _safe_str(item.get("role")),
            "text": _safe_str(item.get("text")),
            "emotion": _safe_str(item.get("emotion")),
        })
    return out


def build_llm_request_payload(
    simulation_state: Dict[str, Any],
    *,
    turn_id: str,
    mode: str = "dialogue",
    scene_state: Dict[str, Any] | None = None,
    dialogue_state: Dict[str, Any] | None = None,
    personality_profile: Dict[str, Any] | None = None,
    extra_constraints: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a deterministic structured payload for an LLM request.

    This function is pure. It does not mutate runtime or orchestration state.
    """
    simulation_state = _safe_dict(simulation_state)
    scene_state = _safe_dict(scene_state)
    dialogue_input_state = _safe_dict(dialogue_state)
    personality_profile = _safe_dict(personality_profile)
    extra_constraints = _safe_dict(extra_constraints)

    runtime_dialogue_state = get_runtime_dialogue_state(simulation_state)
    active_turn = _find_turn(runtime_dialogue_state, turn_id)
    turn_id = _safe_str(turn_id)

    scene_id = _safe_str(scene_state.get("scene_id") or dialogue_input_state.get("scene_id"))
    location_id = _safe_str(scene_state.get("location_id") or dialogue_input_state.get("location_id"))
    topic = _safe_str(dialogue_input_state.get("topic"))

    style_tags = sorted([
        _safe_str(v)
        for v in _safe_list(active_turn.get("style_tags"))
        if _safe_str(v)
    ])

    history = _compact_history(runtime_dialogue_state)

    payload = {
        "mode": _safe_str(mode or "dialogue"),
        "turn": {
            "turn_id": turn_id,
            "sequence_id": _safe_str(active_turn.get("sequence_id")),
            "tick": _safe_int(active_turn.get("tick"), 0),
            "sequence_index": _safe_int(active_turn.get("sequence_index"), 0),
            "actor_id": _safe_str(active_turn.get("actor_id")),
            "speaker_id": _safe_str(active_turn.get("speaker_id")),
            "speaker_name": _safe_str(active_turn.get("speaker_name")),
            "role": _safe_str(active_turn.get("role")),
            "emotion": _safe_str(active_turn.get("emotion") or "neutral"),
            "style_tags": style_tags,
        },
        "context": {
            "scene_id": scene_id,
            "location_id": location_id,
            "topic": topic,
            "history": history,
            "active_sequence_id": _safe_str(runtime_dialogue_state.get("active_sequence_id")),
            "turn_cursor": _safe_int(runtime_dialogue_state.get("turn_cursor"), 0),
        },
        "personality": {
            "actor_id": _safe_str(personality_profile.get("actor_id")),
            "display_name": _safe_str(personality_profile.get("display_name")),
            "tone": _safe_str(personality_profile.get("tone")),
            "voice_style": _safe_str(personality_profile.get("voice_style")),
            "traits": sorted([
                _safe_str(v)
                for v in _safe_list(personality_profile.get("traits"))
                if _safe_str(v)
            ]),
            "style_tags": sorted([
                _safe_str(v)
                for v in _safe_list(personality_profile.get("style_tags"))
                if _safe_str(v)
            ]),
        },
        "constraints": {
            "stay_in_character": True,
            "respect_simulation_authority": True,
            "do_not_invent_world_facts": True,
            "stream_structured_chunks_only": True,
            "allow_emotional_fallback": _safe_bool(extra_constraints.get("allow_emotional_fallback")),
            "max_sentences": max(1, _safe_int(extra_constraints.get("max_sentences"), 3)),
            "max_history_turns": len(history),
        },
    }
    return payload