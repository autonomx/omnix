from __future__ import annotations

from app.rpg.session.fast_turn_recovery import (
    FAST_TURN_RECOVERY_VERSION,
    attach_fast_turn_recovery,
    build_fast_turn_recovery_items,
    build_fast_turn_recovery_payload,
)


def test_build_fast_turn_recovery_items_creates_background_descriptors() -> None:
    result = {
        "turn_id": "turn-7",
        "input_payload": {"command": "Ask Bran about the graveyard"},
        "final_narration": "Bran lowers his voice and warns you about the old road.",
    }
    session = {"manifest": {"session_id": "session-1"}}

    items = build_fast_turn_recovery_items(result, session=session)
    task_types = [item["task_type"] for item in items]

    assert task_types == ["memory", "audit", "summary"]
    assert all(item["format_version"] == FAST_TURN_RECOVERY_VERSION for item in items)
    assert all(item["background_only"] is True for item in items)
    assert items[0]["payload"]["session_id"] == "session-1"
    assert items[0]["payload"]["turn_id"] == "turn-7"


def test_build_fast_turn_recovery_items_can_be_filtered() -> None:
    result = {"player_input": "Look around", "summary": "You scan the rooftop."}

    items = build_fast_turn_recovery_items(result, enabled_tasks=["audit"])

    assert [item["task_type"] for item in items] == ["audit"]


def test_world_update_descriptor_is_added_for_combat_cards() -> None:
    result = {
        "player_input": "Run turn",
        "summary": "The shambler moves.",
        "combat_event_cards": [{"card_type": "movement", "title": "Shambler moves"}],
    }

    payload = build_fast_turn_recovery_payload(result)

    assert payload["queued"] == 4
    assert payload["items"][-1]["task_type"] == "world_update"


def test_attach_fast_turn_recovery_copies_to_nested_result() -> None:
    result = {"ok": True, "result": {"summary": "Done."}}

    attached = attach_fast_turn_recovery(result)

    assert attached["fast_turn_recovery"]["format_version"] == FAST_TURN_RECOVERY_VERSION
    assert attached["result"]["fast_turn_recovery"]["queued"] == attached["fast_turn_recovery"]["queued"]
