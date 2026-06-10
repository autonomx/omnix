from __future__ import annotations

from typing import Any, Mapping

from app.rpg.interactive_cli_state_bundle import attach_interactive_cli_state_bundle_to_turn
from app.rpg.interactive_cli_state_checkpoint import (
    create_interactive_cli_state_checkpoint,
    interactive_cli_state_bundle_checksum,
    restore_interactive_cli_state_bundle_from_checkpoint,
)
from app.rpg.interactive_cli_travel_state import advance_travel_state


_TRAVEL_TO_ROAD = "I leave the tavern and take the road north."
_TRAVEL_TO_OLD_MILL = "I continue toward the old mill."
_TRAVEL_TO_RIVER_TOWN = "I keep following the old road east toward the river town."


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _turn_with_travel_state(command: str, turn_index: int, travel_state: Mapping[str, Any]) -> dict[str, Any]:
    raw_result = {
        "narration": "The route changes according to deterministic travel state.",
        "interactive_cli_travel_state": dict(travel_state),
        "travel_state": dict(travel_state),
    }
    return {
        "turn_index": turn_index,
        "player_input": command,
        "player_action": command,
        "raw_narration": raw_result["narration"],
        "narration": raw_result["narration"],
        "narration_preview": raw_result["narration"],
        "interactive_cli_travel_state": dict(travel_state),
        "travel_state": dict(travel_state),
        "raw_result": raw_result,
        "result": raw_result,
    }


def _travel_bundle(command: str, turn_index: int, travel_state: Mapping[str, Any]) -> dict[str, Any]:
    turn = attach_interactive_cli_state_bundle_to_turn(_turn_with_travel_state(command, turn_index, travel_state))
    return _safe_dict(turn.get("interactive_cli_state_bundle"))


def test_phase13_67_checkpoint_restore_continues_travel_map_expansion() -> None:
    road_state = advance_travel_state(None, _TRAVEL_TO_ROAD)
    old_mill_state = advance_travel_state(road_state, _TRAVEL_TO_OLD_MILL)
    old_mill_bundle = _travel_bundle(_TRAVEL_TO_OLD_MILL, 2, old_mill_state)
    checkpoint = create_interactive_cli_state_checkpoint(
        old_mill_bundle,
        checkpoint_id="travel-old-mill-turn-2",
        turn_index=2,
    )

    restored_bundle = restore_interactive_cli_state_bundle_from_checkpoint(checkpoint)
    restored_travel_state = restored_bundle["states"]["travel"]

    assert checkpoint["bundle_checksum"] == interactive_cli_state_bundle_checksum(old_mill_bundle)
    assert restored_bundle == old_mill_bundle
    assert restored_travel_state["current_location_id"] == "location:old-mill"

    uninterrupted_river_state = advance_travel_state(old_mill_state, _TRAVEL_TO_RIVER_TOWN)
    restored_river_state = advance_travel_state(restored_travel_state, _TRAVEL_TO_RIVER_TOWN)

    assert restored_river_state == uninterrupted_river_state
    assert restored_river_state["current_location_id"] == "location:river-town"
    assert restored_river_state["destination_id"] == "location:river-town"
    assert restored_river_state["direction"] == "east"

    campaign_map_state = restored_river_state["campaign_map_state"]
    assert "location:river-town" in campaign_map_state["locations"]
    assert campaign_map_state["expansions"][-1]["policy"] == "append_on_edge_request"
    assert campaign_map_state["expansions"][-1]["from_location_id"] == "location:old-mill"
    assert campaign_map_state["expansions"][-1]["to_location_id"] == "location:river-town"

    uninterrupted_bundle = _travel_bundle(_TRAVEL_TO_RIVER_TOWN, 3, uninterrupted_river_state)
    restored_continuation_bundle = _travel_bundle(_TRAVEL_TO_RIVER_TOWN, 3, restored_river_state)

    assert restored_continuation_bundle == uninterrupted_bundle
    assert interactive_cli_state_bundle_checksum(restored_continuation_bundle) == interactive_cli_state_bundle_checksum(
        uninterrupted_bundle
    )
