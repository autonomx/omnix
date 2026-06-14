"""Tests for deterministic memory prompt integration."""
from __future__ import annotations

import json

from app.rpg.ai.semantic_action_intelligence import build_semantic_action_prompt
from app.rpg.session.memory_actor import write_actor_memory
from app.rpg.session.memory_prompt import (
    build_relevant_memory_context,
    build_relevant_memory_prompt_block,
)
from app.rpg.session.memory_world import write_world_memory
from app.rpg.session.memory_writer import write_post_turn_memory
from app.rpg.session.turn_grounding import build_turn_grounding_packet


def _payload() -> dict:
    return {
        "authoritative": {
            "turn_id": "turn:7",
            "tick": 7,
            "summary": "Bran warned the player about the quarry road.",
            "location_id": "rusty_flagon",
            "action_type": "dialogue",
            "npc": {
                "id": "bran",
                "line": "Keep your eyes open near the quarry road.",
            },
        }
    }


def _memory_session() -> dict:
    session = {"runtime_state": {}}
    session = write_post_turn_memory(session, _payload(), player_input="I ask Bran about the quarry.")
    session = write_actor_memory(
        session,
        actor_id="bran",
        text="Bran remembers that the player paid for stew without haggling.",
        relationship={"target_id": "player", "axes": {"trust": 2}},
        tags=["stew", "commerce"],
    )
    return write_world_memory(
        session,
        text="A rumor spreads in the Rusty Flagon about lights near the quarry road.",
        event_type="rumor",
        scope="location",
        scope_id="rusty_flagon",
        location_id="rusty_flagon",
        tags=["quarry", "rumor"],
    )


def test_relevant_memory_context_is_bounded_and_grouped():
    session = _memory_session()

    context = build_relevant_memory_context(
        session,
        player_input="Bran, any quarry rumors?",
        actor_ids=["bran"],
        location_id="rusty_flagon",
        limit=3,
    )

    assert context["format_version"] == "rpg_relevant_memory_prompt_v1"
    assert [entry["id"] for entry in context["recent"]] == ["mem:000001", "mem:000002"]
    assert [entry["id"] for entry in context["actors"]] == ["mem:000003"]
    assert [entry["id"] for entry in context["world"]] == ["mem:000004"]
    assert context["usage"] == "continuity_only_runtime_state_remains_authoritative"


def test_relevant_memory_prompt_block_is_explicit_and_deterministic():
    session = _memory_session()
    context = build_relevant_memory_context(
        session,
        player_input="Bran, any quarry rumors?",
        actor_ids=["bran"],
        location_id="rusty_flagon",
    )

    block = build_relevant_memory_prompt_block(context)

    assert block.startswith("Relevant Memory:")
    assert "Usage: continuity only; current runtime state and turn contract remain authoritative." in block
    assert "[mem:000003 | actor | bran | private]" in block
    assert "[mem:000004 | world | rumor | public]" in block


def test_turn_grounding_packet_includes_relevant_memory():
    session = _memory_session()
    runtime_state = session["runtime_state"] | {
        "current_scene": {
            "scene_id": "scene:flagon",
            "location_id": "rusty_flagon",
            "location_name": "Rusty Flagon",
            "present_npc_ids": ["bran"],
        }
    }
    simulation_state = {
        "player_state": {"location_id": "rusty_flagon"},
        "npc_index": {"bran": {"id": "bran", "name": "Bran", "location_id": "rusty_flagon"}},
    }

    packet = build_turn_grounding_packet(
        player_input="Bran, any quarry rumors?",
        simulation_state=simulation_state,
        runtime_state=runtime_state,
    )

    memory = packet["relevant_memory"]
    assert memory["query"]["actor_ids"] == ["bran"]
    assert [entry["id"] for entry in memory["actors"]] == ["mem:000003"]
    assert [entry["id"] for entry in memory["world"]] == ["mem:000004"]


def test_semantic_action_prompt_serializes_relevant_memory_in_input_payload():
    session = _memory_session()
    runtime_state = session["runtime_state"] | {
        "current_scene": {
            "scene_id": "scene:flagon",
            "location_id": "rusty_flagon",
            "location_name": "Rusty Flagon",
            "present_npc_ids": ["bran"],
        }
    }
    simulation_state = {
        "player_state": {"location_id": "rusty_flagon"},
        "npc_index": {"bran": {"id": "bran", "name": "Bran", "location_id": "rusty_flagon"}},
    }

    prompt = build_semantic_action_prompt(
        "Bran, any quarry rumors?",
        simulation_state,
        runtime_state,
        {"action_type": "social_activity", "target_id": "bran"},
    )
    payload = json.loads(prompt.split("INPUT:\n", 1)[1])

    relevant_memory = payload["turn_grounding_packet"]["relevant_memory"]
    assert relevant_memory["format_version"] == "rpg_relevant_memory_prompt_v1"
    assert [entry["id"] for entry in relevant_memory["actors"]] == ["mem:000003"]
    assert "Use relevant_memory only for continuity" in prompt


def test_scene_prompt_includes_relevant_memory_block():
    from app.rpg.ai.world_scene_narrator_prompts import build_scene_prompt

    session = _memory_session()
    prompt = build_scene_prompt(
        {
            "title": "Rusty Flagon",
            "summary": "A smoky tavern near the quarry road.",
            "actors": ["Bran"],
            "location_id": "rusty_flagon",
            "location_name": "Rusty Flagon",
        },
        {
            "runtime_state": session["runtime_state"],
            "simulation_state": {"player_state": {"location_id": "rusty_flagon"}},
            "player_input": "Bran, any quarry rumors?",
            "turn_contract": {
                "narration_brief": "Bran answers the player's question about quarry rumors.",
                "interpreted_action": {"target_id": "bran", "target_name": "Bran"},
            },
        },
    )

    assert "Relevant Memory:" in prompt
    assert "Bran remembers that the player paid for stew without haggling." in prompt
    assert "Relevant Memory never authorizes new rewards" in prompt
