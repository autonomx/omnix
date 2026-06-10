from __future__ import annotations

from typing import Any, Mapping

from app.rpg.interactive_cli_state_bundle import (
    INTERACTIVE_CLI_STATE_BUNDLE_PATCH,
    apply_interactive_cli_state_bundle_to_matrix_result,
)
from tests.rpg.test_ci_phase13_62_feature_state_regression import (
    _apply_all_feature_state_cleanups,
    _result_for,
    _state_matrix_result,
)


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _last_bundle(cleaned_result: Mapping[str, Any], scenario_id: str) -> dict[str, Any]:
    turns = _result_for(cleaned_result, scenario_id)["turns"]
    assert turns, f"missing turns for {scenario_id}"
    bundle = _safe_dict(turns[-1].get("interactive_cli_state_bundle"))
    assert bundle.get("patch") == INTERACTIVE_CLI_STATE_BUNDLE_PATCH
    return bundle


def test_phase13_65_interactive_state_bundle_collects_feature_state_layers() -> None:
    result = _apply_all_feature_state_cleanups(_state_matrix_result())

    bundle_cleanup = apply_interactive_cli_state_bundle_to_matrix_result(result)

    assert bundle_cleanup["ok"] is True
    assert bundle_cleanup["patch"] == INTERACTIVE_CLI_STATE_BUNDLE_PATCH
    assert bundle_cleanup["changed_turns"] == 12
    assert result["summary"]["interactive_cli_state_bundle"]["changed_turns"] == 12

    commerce_states = _last_bundle(result, "shop_sell_attempt")["states"]
    assert len(commerce_states["commerce"]["attempted_sells"]) == 3
    assert commerce_states["commerce"]["inventory_mutated"] is False
    assert commerce_states["commerce"]["currency_delta_copper"] == 0

    travel_states = _last_bundle(result, "travel_round_trip_route")["states"]
    assert travel_states["travel"]["current_location_id"] == "location:tavern"
    assert travel_states["campaign_map"]["seed_scope"] == "local_region_seed"

    memory_states = _last_bundle(result, "npc_memory_recall_probe")["states"]
    assert memory_states["memory"]["facts"]["trail_name"] == "Ash Lantern"
    assert memory_states["memory"]["remembered_by"]["trail_name"] == "Bran"

    equipment_states = _last_bundle(result, "equipment_inventory_probe")["states"]
    assert equipment_states["equipment"]["readied_items"] == ["sword", "shield"]
    assert "ration" in equipment_states["equipment"]["carried_items"]


def test_phase13_65_bundle_is_written_to_raw_result_too() -> None:
    result = _apply_all_feature_state_cleanups(_state_matrix_result())
    apply_interactive_cli_state_bundle_to_matrix_result(result)

    turn = _result_for(result, "npc_memory_recall_probe")["turns"][-1]
    raw_bundle = _safe_dict(_safe_dict(turn.get("raw_result")).get("interactive_cli_state_bundle"))
    assert raw_bundle.get("patch") == INTERACTIVE_CLI_STATE_BUNDLE_PATCH
    assert raw_bundle["states"]["memory"]["facts"]["trail_name"] == "Ash Lantern"
