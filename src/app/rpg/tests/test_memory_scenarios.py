"""Scenario-level deterministic tests for RPG memory roadmap PR 8."""
from __future__ import annotations

import json
from copy import deepcopy

from app.rpg.ai.memory_narration_grounding import validate_memory_narration_text
from app.rpg.session.memory_actor import get_relevant_actor_memory, write_actor_memory
from app.rpg.session.memory_debug_report import build_memory_debug_report_payload
from app.rpg.session.memory_prompt import (
    build_relevant_memory_context,
    build_relevant_memory_prompt_block,
)
from app.rpg.session.memory_retrieval import get_relevant_recent_memory
from app.rpg.session.memory_world import get_world_memory, write_world_memory
from app.rpg.session.memory_writer import write_post_turn_memory


def _turn_payload(
    *,
    turn_id: str,
    tick: int,
    summary: str,
    npc_id: str = "",
    npc_line: str = "",
    location_id: str = "rusty_flagon",
    action_type: str = "dialogue",
) -> dict:
    return {
        "authoritative": {
            "turn_id": turn_id,
            "tick": tick,
            "summary": summary,
            "location_id": location_id,
            "action_type": action_type,
            "npc": {"id": npc_id, "line": npc_line},
        }
    }


def _bran_session() -> dict:
    session = {"session_id": "bran-memory", "runtime_state": {}}
    session = write_post_turn_memory(
        session,
        _turn_payload(
            turn_id="turn:1",
            tick=1,
            summary="The player entered the old mill room with Bran.",
            npc_id="bran",
            npc_line="This room always smells of wet flour.",
            location_id="old_mill",
        ),
        player_input="I enter the old mill room with Bran.",
    )
    session = write_post_turn_memory(
        session,
        _turn_payload(
            turn_id="turn:2",
            tick=2,
            summary="The player shared a ration with Bran.",
            npc_id="bran",
            npc_line="I will remember the ration you shared.",
            location_id="old_mill",
        ),
        player_input="I give Bran a trail ration.",
    )
    return write_actor_memory(
        session,
        actor_id="bran",
        text="Bran remembers the player shared a trail ration in the old mill room.",
        location_id="old_mill",
        relationship={"target_id": "player", "axes": {"trust": 2}},
        tags=["ration", "old_mill", "room"],
    )


def test_bran_memory_retrieves_prior_room_ration_and_dialogue_facts():
    session = _bran_session()

    recent = get_relevant_recent_memory(
        session,
        npc_id="bran",
        query_terms=["ration", "room"],
    )
    context = build_relevant_memory_context(
        session,
        player_input="Bran, do you remember the ration and that old room?",
        actor_ids=["bran"],
        location_id="old_mill",
        query_terms=["ration", "room"],
    )
    block = build_relevant_memory_prompt_block(context)

    assert [entry["id"] for entry in recent] == [
        "mem:000001",
        "mem:000002",
        "mem:000003",
        "mem:000004",
    ]
    assert [entry["id"] for entry in context["actors"]] == ["mem:000005"]
    assert "trail ration in the old mill room" in block
    assert "Relevant Memory never authorizes" not in block


def test_elara_shop_interaction_is_actor_scoped():
    session = write_actor_memory(
        {"session_id": "shop-memory", "runtime_state": {}},
        actor_id="elara",
        text="Elara remembers the player bought lamp oil from her market stall.",
        location_id="market_square",
        visibility="private",
        tags=["shop", "lamp_oil"],
    )
    session = write_actor_memory(
        session,
        actor_id="bran",
        text="Bran remembers only a tavern meal.",
        location_id="rusty_flagon",
        tags=["meal"],
    )

    elara = get_relevant_actor_memory(session, "elara", query_terms=["lamp_oil"])
    context = build_relevant_memory_context(
        session,
        player_input="Elara, do you remember the lamp oil?",
        actor_ids=["elara"],
        location_id="market_square",
        query_terms=["lamp_oil"],
    )

    assert [entry["id"] for entry in elara] == ["mem:000001"]
    assert [entry["actor_id"] for entry in context["actors"]] == ["elara"]
    assert all("Bran" not in entry["text"] for entry in context["actors"])


def test_guard_public_events_respect_visibility_filters():
    session = write_world_memory(
        {"session_id": "guard-events", "runtime_state": {}},
        text="The north gate guards publicly reported bandit tracks near the road.",
        event_type="guard_report",
        scope="location",
        scope_id="north_gate",
        location_id="north_gate",
        visibility="public",
        tags=["guards", "bandits"],
    )
    session = write_world_memory(
        session,
        text="A guard privately suspects the captain is hiding a bribe.",
        event_type="guard_suspicion",
        scope="faction",
        scope_id="town_guard",
        location_id="north_gate",
        visibility="private",
        tags=["guards", "bribe"],
    )

    public_events = get_world_memory(session, location_id="north_gate", visibility="public")
    private_events = get_world_memory(session, location_id="north_gate", visibility="private")

    assert [entry["id"] for entry in public_events] == ["mem:000001"]
    assert "publicly reported bandit tracks" in public_events[0]["text"]
    assert [entry["id"] for entry in private_events] == ["mem:000002"]
    assert all(entry["visibility"] == "public" for entry in public_events)


def test_quest_clue_grounding_retrieves_clue_without_hallucinated_memory():
    session = write_world_memory(
        {"session_id": "quest-clue", "runtime_state": {}},
        text="The missing caravan clue points from the quarry road toward the old shrine.",
        event_type="quest_clue",
        scope="quest",
        scope_id="missing_caravan",
        location_id="quarry_road",
        visibility="public",
        tags=["missing_caravan", "shrine"],
    )
    context = build_relevant_memory_context(
        session,
        player_input="What clue do I remember about the missing caravan?",
        location_id="quarry_road",
        query_terms=["missing_caravan", "shrine"],
    )
    validation_context = {
        "runtime_state": session["runtime_state"],
        "player_input": "What clue do I remember about the missing caravan?",
        "relevant_memory": context,
    }

    backed = validate_memory_narration_text(
        "You remember the missing caravan clue points toward the old shrine.",
        validation_context,
    )
    hallucinated = validate_memory_narration_text(
        "You remember a moonstone locket was hidden under Bran's counter.",
        validation_context,
    )

    assert [entry["id"] for entry in context["world"]] == ["mem:000001"]
    assert "moonstone" not in build_relevant_memory_prompt_block(context)
    assert backed["ok"] is True
    assert hallucinated["ok"] is False


def test_memory_replay_is_deterministic_with_serialized_state():
    session = _bran_session()
    serialized_session = json.loads(json.dumps(session, sort_keys=True))
    original = deepcopy(serialized_session)

    first_context = build_relevant_memory_context(
        serialized_session,
        player_input="Bran, remember the ration?",
        actor_ids=["bran"],
        location_id="old_mill",
        query_terms=["ration"],
    )
    second_context = build_relevant_memory_context(
        json.loads(json.dumps(serialized_session, sort_keys=True)),
        player_input="Bran, remember the ration?",
        actor_ids=["bran"],
        location_id="old_mill",
        query_terms=["ration"],
    )
    first_report = build_memory_debug_report_payload(
        {"turn_index": 3, "raw_result": {"session": serialized_session, "relevant_memory": first_context}}
    )
    second_report = build_memory_debug_report_payload(
        {"turn_index": 3, "raw_result": {"session": serialized_session, "relevant_memory": second_context}}
    )

    assert first_context == second_context
    assert first_report == second_report
    assert serialized_session == original
