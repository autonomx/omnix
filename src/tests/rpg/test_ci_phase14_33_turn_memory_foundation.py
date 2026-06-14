from __future__ import annotations

from types import ModuleType

from app.rpg.session.turn_memory_contract import (
    attach_turn_memory_context_with_session,
    retrieve_relevant_memories,
    write_turn_memory,
)
from app.rpg.session.turn_memory_runtime_hook import (
    attach_turn_memory_to_runtime_result,
    force_install_turn_memory_runtime_hook_for_tests,
)


def _session() -> dict:
    return {
        "manifest": {"session_id": "session-memory-1"},
        "simulation_state": {"current_location_id": "loc:rusty_flagon", "location_name": "Rusty Flagon"},
        "runtime_state": {"tick": 1},
    }


def _bran_result(*, tick: int = 1, player_input: str = "") -> dict:
    return {
        "ok": True,
        "turn_id": f"turn-{tick}",
        "tick": tick,
        "action_type": "npc_interpretive_dialogue",
        "summary": "Bran answers carefully.",
        "npc": {"id": "npc:bran", "speaker": "Bran", "line": "I'll remember what matters."},
        "result": {
            "action_type": "npc_interpretive_dialogue",
            "summary": "Bran answers carefully.",
            "npc": {"id": "npc:bran", "speaker": "Bran", "line": "I'll remember what matters."},
        },
        "simulation_state": {"current_location_id": "loc:rusty_flagon", "location_name": "Rusty Flagon"},
        "runtime_state": {"tick": tick},
        "player_input": player_input,
    }


def test_turn_memory_writes_recent_turn_and_dialogue_fact() -> None:
    updated_session, written = write_turn_memory(
        _session(),
        _bran_result(player_input="Bran, my trail name is Red Fox."),
        player_input="Bran, my trail name is Red Fox.",
    )

    memory = updated_session["runtime_state"]["turn_memory"]
    assert memory["format_version"] == "rpg_turn_memory_contract_v1"
    assert len(memory["recent_turns"]) == 1
    assert len(memory["dialogue_memories"]) == 1
    assert written["facts"] == [
        {"type": "identity_alias", "subject": "player", "key": "trail_name", "value": "Red Fox"}
    ]
    assert memory["dialogue_memories"][0]["listener_ids"] == ["npc:bran"]
    assert memory["dialogue_memories"][0]["visibility"] == "private"


def test_turn_memory_retrieves_private_bran_memory_for_bran_recall() -> None:
    session_after_fact, _ = write_turn_memory(
        _session(),
        _bran_result(tick=1, player_input="Bran, my trail name is Red Fox."),
        player_input="Bran, my trail name is Red Fox.",
    )
    session_after_filler, _ = write_turn_memory(
        session_after_fact,
        _bran_result(tick=2, player_input="What food is on hand?"),
        player_input="What food is on hand?",
    )

    retrieved = retrieve_relevant_memories(
        session_after_filler["runtime_state"]["turn_memory"],
        player_input="Bran, do you remember my trail name?",
        addressed_actor_id="npc:bran",
        location_id="loc:rusty_flagon",
    )

    assert retrieved
    assert retrieved[0]["facts"][0]["value"] == "Red Fox"
    assert retrieved[0]["listener_ids"] == ["npc:bran"]


def test_turn_memory_hides_private_bran_memory_from_guard() -> None:
    session_after_fact, _ = write_turn_memory(
        _session(),
        _bran_result(tick=1, player_input="Bran, my trail name is Red Fox."),
        player_input="Bran, my trail name is Red Fox.",
    )

    retrieved = retrieve_relevant_memories(
        session_after_fact["runtime_state"]["turn_memory"],
        player_input="Guard, do you remember my trail name?",
        addressed_actor_id="npc:guard",
        location_id="loc:rusty_flagon",
    )

    assert retrieved == []


def test_attach_turn_memory_context_adds_top_level_and_nested_payload() -> None:
    result, updated_session = attach_turn_memory_context_with_session(
        _bran_result(tick=1, player_input="My trail name is Red Fox."),
        session=_session(),
        player_input="My trail name is Red Fox.",
    )

    assert result["turn_memory"]["deterministic"] is True
    assert result["turn_memory"]["dialogue_memory_count"] == 1
    assert result["result"]["turn_memory"]["written"]["facts"][0]["value"] == "Red Fox"
    assert updated_session["runtime_state"]["turn_memory"]["dialogue_memories"][0]["facts"][0]["value"] == "Red Fox"


def test_runtime_hook_wraps_apply_turn_and_preserves_result() -> None:
    module = ModuleType("fake_interactive_memory_runtime")
    calls: list[tuple[str, str]] = []

    def apply_turn(session_id: str, player_input: str, **kwargs):
        calls.append((session_id, player_input))
        return _bran_result(tick=3, player_input=player_input)

    module.apply_turn = apply_turn  # type: ignore[attr-defined]

    assert force_install_turn_memory_runtime_hook_for_tests(module) is True
    result = module.apply_turn("session-memory-1", "Bran, my trail name is Red Fox.", session_override=_session())  # type: ignore[attr-defined]

    assert calls == [("session-memory-1", "Bran, my trail name is Red Fox.")]
    assert result["ok"] is True
    assert result["turn_memory_runtime_hook"]["attached"] is True
    assert result["turn_memory"]["written"]["facts"][0]["value"] == "Red Fox"


def test_runtime_hook_reports_noop_for_non_dict_results() -> None:
    module = ModuleType("fake_interactive_memory_runtime_non_dict")

    def apply_turn(*args, **kwargs):
        return "not-a-dict"

    module.apply_turn = apply_turn  # type: ignore[attr-defined]
    assert force_install_turn_memory_runtime_hook_for_tests(module) is True
    assert module.apply_turn("session-memory-1", "What now?") == "not-a-dict"  # type: ignore[attr-defined]


def test_attach_turn_memory_runtime_result_reports_payload_without_persistence_for_override() -> None:
    result = attach_turn_memory_to_runtime_result(
        _bran_result(tick=4, player_input="Bran, my name is Mara."),
        call_context={"session_id": "", "player_input": "Bran, my name is Mara.", "session_override": _session()},
    )

    assert result["turn_memory_runtime_hook"]["attached"] is True
    assert result["turn_memory_runtime_hook"]["persisted"] is False
    assert result["turn_memory"]["written"]["facts"][0] == {
        "type": "identity_alias",
        "subject": "player",
        "key": "name",
        "value": "Mara",
    }
