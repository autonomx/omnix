from __future__ import annotations

import json

from app.rpg.session.canonical_direct_dialogue import build_canonical_direct_dialogue_intent
from app.rpg.session.dialogue_focus import record_direct_dialogue_exchange
from app.rpg.session.turn_grounding import build_turn_grounding_packet


def _session() -> dict:
    return {
        "manifest": {"session_id": "dialogue-focus-test"},
        "simulation_state": {
            "player_state": {
                "location_id": "loc:tavern",
                "nearby_npc_ids": ["npc:bran", "npc:elara"],
            },
            "npc_index": {
                "npc:bran": {
                    "id": "npc:bran",
                    "name": "Bran",
                    "role": "innkeeper",
                    "location_id": "loc:tavern",
                },
                "npc:elara": {
                    "id": "npc:elara",
                    "name": "Elara",
                    "role": "merchant",
                    "location_id": "loc:tavern",
                },
            },
        },
        "runtime_state": {
            "tick": 41,
            "current_scene": {
                "scene_id": "scene:tavern",
                "location_id": "loc:tavern",
                "location_name": "Rusty Flagon Tavern",
                "present_npc_ids": ["npc:bran", "npc:elara"],
            },
        },
    }


def _bran_question_result() -> dict:
    resolution = {
        "target_id": "npc:bran",
        "target_name": "Bran",
        "resolution_source": "explicit_input",
        "candidate_target_ids": ["npc:bran"],
        "confidence": 1.0,
        "locked": True,
        "ambiguous": False,
        "requires_clarification": False,
        "source": "deterministic_dialogue_focus_v1",
    }
    resolved = {
        "ok": True,
        "action_type": "npc_interpretive_dialogue",
        "semantic_family": "social",
        "response_mode": "dialogue",
        "target_id": "npc:bran",
        "target_name": "Bran",
        "dialogue_resolution": resolution,
    }
    return {
        "ok": True,
        "result": dict(resolved),
        "resolved_result": dict(resolved),
        "dialogue_resolution": resolution,
        "npc": {"speaker_id": "npc:bran", "speaker": "Bran"},
        "visible_response": {
            "narration": "Bran surveys the quiet common room.",
            "npc": {
                "speaker_id": "npc:bran",
                "speaker": "Bran",
                "line": "Did the old road seem unusually quiet to you?",
            },
        },
    }


def _record_bran_exchange(session: dict) -> dict:
    result = _bran_question_result()
    recorded = record_direct_dialogue_exchange(
        session=session,
        player_input="I ask Bran how business is going.",
        result=result,
        tick=41,
        turn_id="turn:41",
        persist=False,
    )
    assert recorded["recorded"] is True
    return result


def test_declarative_reply_inherits_bran_with_multiple_npcs_after_roundtrip() -> None:
    session = _session()
    _record_bran_exchange(session)

    reloaded = json.loads(json.dumps(session))
    reloaded["runtime_state"]["tick"] = 42
    packet = build_turn_grounding_packet(
        player_input="The old road was indeed quiet and peaceful.",
        simulation_state=reloaded["simulation_state"],
        runtime_state=reloaded["runtime_state"],
        candidate_action={},
    )

    resolution = packet["priority_context"]["dialogue_resolution"]
    assert packet["priority_context"]["addressed_npc_ids"] == ["npc:bran"]
    assert resolution["target_id"] == "npc:bran"
    assert resolution["resolution_source"] == "active_thread"
    assert resolution["reply_to_beat_id"]
    assert resolution["candidate_target_ids"] == ["npc:bran"]
    assert resolution["locked"] is True

    transcript = packet["priority_context"]["dialogue_context"]["recent_turns"]
    assert [turn["speaker_id"] for turn in transcript] == ["player", "npc:bran"]
    assert transcript[0]["target_id"] == "npc:bran"
    assert transcript[1]["target_id"] == "player"
    assert transcript[1]["text"] == "Did the old road seem unusually quiet to you?"


def test_canonical_dialogue_uses_locked_thread_target_and_never_unknown() -> None:
    session = _session()
    _record_bran_exchange(session)
    session = json.loads(json.dumps(session))
    session["runtime_state"]["tick"] = 42
    player_input = "The old road was indeed quiet and peaceful."
    packet = build_turn_grounding_packet(
        player_input=player_input,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
    )
    semantic_advisory = {
        "action_type": "social_activity",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "stateful": False,
        "needs_runtime_resolution": False,
        "first_call_grounding_diagnostics": {"turn_grounding_packet": packet},
    }

    intent = build_canonical_direct_dialogue_intent(
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
        player_input=player_input,
        action_advisory={},
        semantic_advisory=semantic_advisory,
    )

    assert intent["ok"] is True
    assert intent["npc"]["speaker_id"] == "npc:bran"
    assert intent["resolved_result"]["target_id"] == "npc:bran"
    assert intent["resolved_result"]["reply_to_beat_id"]
    assert "unknown" not in json.dumps(intent).casefold()


def test_explicit_retarget_overrides_active_bran_thread() -> None:
    session = _session()
    _record_bran_exchange(session)
    session["runtime_state"]["tick"] = 42

    packet = build_turn_grounding_packet(
        player_input="Elara, what have you heard about the road?",
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
    )

    resolution = packet["priority_context"]["dialogue_resolution"]
    assert resolution["target_id"] == "npc:elara"
    assert resolution["resolution_source"] == "explicit_input"
    assert packet["priority_context"]["addressed_npc_ids"] == ["npc:elara"]


def test_genuine_ambiguity_requests_clarification_without_unknown_speaker() -> None:
    session = _session()
    player_input = "It was quiet and peaceful."
    packet = build_turn_grounding_packet(
        player_input=player_input,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
    )
    semantic_advisory = {
        "action_type": "social_activity",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "stateful": False,
        "needs_runtime_resolution": False,
        "first_call_grounding_diagnostics": {"turn_grounding_packet": packet},
    }

    intent = build_canonical_direct_dialogue_intent(
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
        player_input=player_input,
        action_advisory={},
        semantic_advisory=semantic_advisory,
    )

    assert packet["priority_context"]["dialogue_resolution"]["requires_clarification"] is True
    assert intent["consumed"] is True
    assert intent["ok"] is False
    assert intent["clarification"] == "Who are you speaking to?"
    assert intent["visible_response"]["npc"] == {}
    assert "unknown" not in json.dumps(intent).casefold()
