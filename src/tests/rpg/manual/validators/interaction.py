from __future__ import annotations

from typing import Any, Dict, List

from tests.rpg.manual.extractors.interaction import (
    _interaction_reason_is,
    _interaction_taken_item,
)


def validate_interaction_l1_l3_turn(
    *,
    scenario_name: str,
    summary_row: Dict[str, Any],
) -> List[str]:
    warnings: List[str] = []

    if scenario_name == "interaction_open_unlocked_chest":
        if not _interaction_reason_is(summary_row, "opened"):
            warnings.append("interaction_unlocked_chest_not_opened")

    if scenario_name == "interaction_unlock_chest_with_key":
        if not _interaction_reason_is(summary_row, "unlocked"):
            warnings.append("interaction_chest_with_key_not_unlocked")

    if scenario_name == "interaction_unlock_chest_without_key_fails":
        if not _interaction_reason_is(summary_row, "missing_required_item"):
            warnings.append("interaction_chest_without_key_did_not_fail")

    if scenario_name == "interaction_open_locked_chest_fails":
        if not _interaction_reason_is(summary_row, "target_locked"):
            warnings.append("interaction_locked_chest_open_did_not_fail")

    if scenario_name == "interaction_take_item_from_closed_chest_fails":
        if not _interaction_reason_is(summary_row, "container_closed"):
            warnings.append("interaction_closed_chest_take_did_not_fail")

    if scenario_name == "interaction_take_item_from_open_chest_succeeds":
        if not _interaction_reason_is(summary_row, "items_taken"):
            warnings.append("interaction_open_chest_items_not_taken")
        if not _interaction_taken_item(summary_row, "item:copper_coin"):
            warnings.append("interaction_open_chest_missing_taken_item")

    if scenario_name == "interaction_unlock_door_with_key":
        if not _interaction_reason_is(summary_row, "unlocked"):
            warnings.append("interaction_door_with_key_not_unlocked")

    if scenario_name == "interaction_unlock_door_without_key_fails":
        if not _interaction_reason_is(summary_row, "missing_required_item"):
            warnings.append("interaction_door_without_key_did_not_fail")

    return warnings


def validate_interaction_l1_l3_scenario(
    *,
    scenario_name: str,
    scenario_results: List[Dict[str, Any]],
) -> List[str]:
    warnings: List[str] = []

    def any_reason(reason: str) -> bool:
        return any(_interaction_reason_is(row, reason) for row in scenario_results)

    if scenario_name == "interaction_open_unlocked_chest" and not any_reason("opened"):
        warnings.append("interaction_unlocked_chest_not_opened")

    if scenario_name == "interaction_unlock_chest_with_key" and not any_reason("unlocked"):
        warnings.append("interaction_chest_with_key_not_unlocked")

    if scenario_name == "interaction_unlock_chest_without_key_fails" and not any_reason("missing_required_item"):
        warnings.append("interaction_chest_without_key_did_not_fail")

    if scenario_name == "interaction_open_locked_chest_fails" and not any_reason("target_locked"):
        warnings.append("interaction_locked_chest_open_did_not_fail")

    if scenario_name == "interaction_take_item_from_closed_chest_fails" and not any_reason("container_closed"):
        warnings.append("interaction_closed_chest_take_did_not_fail")

    if scenario_name == "interaction_take_item_from_open_chest_succeeds":
        if not any_reason("items_taken"):
            warnings.append("interaction_open_chest_items_not_taken")
        if not any(_interaction_taken_item(row, "item:copper_coin") for row in scenario_results):
            warnings.append("interaction_open_chest_missing_taken_item")

    if scenario_name == "interaction_unlock_door_with_key" and not any_reason("unlocked"):
        warnings.append("interaction_door_with_key_not_unlocked")

    if scenario_name == "interaction_unlock_door_without_key_fails" and not any_reason("missing_required_item"):
        warnings.append("interaction_door_without_key_did_not_fail")

    return warnings