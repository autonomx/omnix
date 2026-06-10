from __future__ import annotations

from typing import Any, Callable, Mapping

from app.rpg.interactive_cli_commerce_state import apply_sell_attempt, default_commerce_state
from app.rpg.interactive_cli_equipment_state import apply_ready_command, default_equipment_state
from app.rpg.interactive_cli_memory_state import default_short_session_memory_state, remember_trail_name
from app.rpg.interactive_cli_state_bundle import attach_interactive_cli_state_bundle_to_turn
from app.rpg.interactive_cli_state_checkpoint import (
    create_interactive_cli_state_checkpoint,
    deserialize_interactive_cli_state_checkpoint,
    interactive_cli_state_bundle_checksum,
    restore_interactive_cli_state_bundle_from_checkpoint,
    serialize_interactive_cli_state_checkpoint,
)
from app.rpg.interactive_cli_travel_state import advance_travel_state

_TRAVEL_TO_ROAD = "I leave the tavern and take the road north."
_TRAVEL_TO_OLD_MILL = "I continue toward the old mill."
_TRAVEL_TO_RIVER_TOWN = "I keep following the old road east toward the river town."
_SELL_RATION = "I ask Bran how much copper he would give me for one ration."
_REMEMBER_TRAIL_NAME = "Bran, remember this: my trail name is Ash Lantern."
_READY_GEAR = "I ready my sword and shield."


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _turn(command: str, turn_index: int, states: Mapping[str, Any]) -> dict[str, Any]:
    raw_result: dict[str, Any] = {"narration": "Replay state advances deterministically."}
    turn: dict[str, Any] = {
        "turn_index": turn_index,
        "player_input": command,
        "player_action": command,
        "raw_narration": raw_result["narration"],
        "narration": raw_result["narration"],
        "narration_preview": raw_result["narration"],
        "raw_result": raw_result,
        "result": raw_result,
    }
    for key, state in states.items():
        turn[key] = dict(state)
        raw_result[key] = dict(state)
    return turn


def _bundle(command: str, turn_index: int, states: Mapping[str, Any]) -> dict[str, Any]:
    bundled = attach_interactive_cli_state_bundle_to_turn(_turn(command, turn_index, states))
    return _safe_dict(bundled.get("interactive_cli_state_bundle"))


def _checkpoint_round_trip(bundle: Mapping[str, Any], checkpoint_id: str) -> dict[str, Any]:
    checkpoint = create_interactive_cli_state_checkpoint(bundle, checkpoint_id=checkpoint_id)
    serialized = serialize_interactive_cli_state_checkpoint(checkpoint)
    return deserialize_interactive_cli_state_checkpoint(serialized)


def _replay_twice(
    checkpoint: Mapping[str, Any],
    replay: Callable[[Mapping[str, Any]], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    restored_a = restore_interactive_cli_state_bundle_from_checkpoint(checkpoint)
    restored_b = restore_interactive_cli_state_bundle_from_checkpoint(checkpoint)
    return replay(restored_a), replay(restored_b)


def test_phase13_69_checkpoint_replay_is_deterministic_for_equipment() -> None:
    initial_bundle = _bundle(
        "I check my inventory and gear.",
        1,
        {"interactive_cli_equipment_state": default_equipment_state()},
    )
    checkpoint = _checkpoint_round_trip(initial_bundle, "equipment-before-ready")

    def replay(restored_bundle: Mapping[str, Any]) -> dict[str, Any]:
        equipment_state = restored_bundle["states"]["equipment"]
        ready_state = apply_ready_command(equipment_state)
        return _bundle(_READY_GEAR, 2, {"interactive_cli_equipment_state": ready_state})

    first, second = _replay_twice(checkpoint, replay)

    assert first == second
    assert first["states"]["equipment"]["readied_items"] == ["sword", "shield"]
    assert interactive_cli_state_bundle_checksum(first) == interactive_cli_state_bundle_checksum(second)


def test_phase13_69_checkpoint_replay_is_deterministic_for_memory() -> None:
    initial_bundle = _bundle(
        "I greet Bran.",
        1,
        {"interactive_cli_memory_state": default_short_session_memory_state()},
    )
    checkpoint = _checkpoint_round_trip(initial_bundle, "memory-before-trail-name")

    def replay(restored_bundle: Mapping[str, Any]) -> dict[str, Any]:
        memory_state = restored_bundle["states"]["memory"]
        remembered_state = remember_trail_name(memory_state, "Ash Lantern", npc_name="Bran")
        return _bundle(_REMEMBER_TRAIL_NAME, 2, {"interactive_cli_memory_state": remembered_state})

    first, second = _replay_twice(checkpoint, replay)

    assert first == second
    assert first["states"]["memory"]["facts"]["trail_name"] == "Ash Lantern"
    assert first["states"]["memory"]["remembered_by"]["trail_name"] == "Bran"
    assert interactive_cli_state_bundle_checksum(first) == interactive_cli_state_bundle_checksum(second)


def test_phase13_69_checkpoint_replay_is_deterministic_for_commerce() -> None:
    initial_bundle = _bundle(
        "I ask Bran about trade.",
        1,
        {"interactive_cli_commerce_state": default_commerce_state()},
    )
    checkpoint = _checkpoint_round_trip(initial_bundle, "commerce-before-sell-attempt")

    def replay(restored_bundle: Mapping[str, Any]) -> dict[str, Any]:
        commerce_state = restored_bundle["states"]["commerce"]
        sell_state = apply_sell_attempt(commerce_state, player_input=_SELL_RATION, turn_index=2)
        return _bundle(_SELL_RATION, 2, {"interactive_cli_commerce_state": sell_state})

    first, second = _replay_twice(checkpoint, replay)

    assert first == second
    assert first["states"]["commerce"]["inventory_mutated"] is False
    assert first["states"]["commerce"]["currency_delta_copper"] == 0
    assert first["states"]["commerce"]["attempted_sells"][-1]["outcome"] == "unsupported_buyback_refusal"
    assert interactive_cli_state_bundle_checksum(first) == interactive_cli_state_bundle_checksum(second)


def test_phase13_69_checkpoint_replay_is_deterministic_for_travel_expansion() -> None:
    road_state = advance_travel_state(None, _TRAVEL_TO_ROAD)
    old_mill_state = advance_travel_state(road_state, _TRAVEL_TO_OLD_MILL)
    old_mill_bundle = _bundle(_TRAVEL_TO_OLD_MILL, 2, {"interactive_cli_travel_state": old_mill_state})
    checkpoint = _checkpoint_round_trip(old_mill_bundle, "travel-old-mill-before-expansion")

    def replay(restored_bundle: Mapping[str, Any]) -> dict[str, Any]:
        travel_state = restored_bundle["states"]["travel"]
        river_state = advance_travel_state(travel_state, _TRAVEL_TO_RIVER_TOWN)
        return _bundle(_TRAVEL_TO_RIVER_TOWN, 3, {"interactive_cli_travel_state": river_state})

    first, second = _replay_twice(checkpoint, replay)

    assert first == second
    assert first["states"]["travel"]["current_location_id"] == "location:river-town"
    assert first["states"]["campaign_map"]["expansions"][-1]["policy"] == "append_on_edge_request"
    assert first["states"]["campaign_map"]["expansions"][-1]["to_location_id"] == "location:river-town"
    assert interactive_cli_state_bundle_checksum(first) == interactive_cli_state_bundle_checksum(second)
