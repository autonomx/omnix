from __future__ import annotations

from typing import Any, Dict

from tests.rpg.manual.extractors.base import (
    _extract_nested_dict_by_key,
    _extract_turn_contract,
    _first_dict,
)
from tests.rpg.manual.safe import _safe_dict, _safe_list, _safe_str


def _extract_interaction_result(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    nested_result = _safe_dict(result_sub.get("result"))
    resolved_result = _safe_dict(result.get("resolved_result"))
    result_resolved = _safe_dict(result_sub.get("resolved_result"))

    turn_contract = _extract_turn_contract(result)
    contract_resolved = _safe_dict(
        turn_contract.get("resolved_result")
        or turn_contract.get("resolved_action")
    )

    candidates = [
        result.get("general_interaction_result"),
        result_sub.get("general_interaction_result"),
        nested_result.get("general_interaction_result"),
        resolved_result.get("general_interaction_result"),
        result_resolved.get("general_interaction_result"),
        turn_contract.get("general_interaction_result"),
        contract_resolved.get("general_interaction_result"),
        result.get("interaction_result"),
        result_sub.get("interaction_result"),
        nested_result.get("interaction_result"),
        resolved_result.get("interaction_result"),
        result_resolved.get("interaction_result"),
        turn_contract.get("interaction_result"),
        contract_resolved.get("interaction_result"),
    ]

    for candidate in candidates:
        candidate = _safe_dict(candidate)
        if candidate:
            return candidate

    return {}


def _extract_general_interaction_result(turn_summary: Dict[str, Any]) -> Dict[str, Any]:
    return _first_dict(
        turn_summary.get("general_interaction_result"),
        turn_summary.get("interaction_result"),
        _safe_dict(turn_summary.get("resolved_result")).get("general_interaction_result"),
        _safe_dict(turn_summary.get("resolved_result")).get("interaction_result"),
        _safe_dict(turn_summary.get("result")).get("general_interaction_result"),
        _safe_dict(turn_summary.get("result")).get("interaction_result"),
        _extract_nested_dict_by_key(turn_summary, "general_interaction_result"),
        _extract_nested_dict_by_key(turn_summary, "interaction_result"),
    )


def _interaction_reason_is(turn_summary: Dict[str, Any], reason: str) -> bool:
    result = _extract_general_interaction_result(turn_summary)
    return _safe_str(result.get("reason")) == reason


def _interaction_resolved(turn_summary: Dict[str, Any]) -> bool:
    return _extract_general_interaction_result(turn_summary).get("resolved") is True


def _interaction_state_change_kind(turn_summary: Dict[str, Any], kind: str) -> bool:
    result = _extract_general_interaction_result(turn_summary)
    for change in _safe_list(result.get("state_changes")):
        if _safe_str(_safe_dict(change).get("kind")) == kind:
            return True
    return False


def _interaction_taken_item(turn_summary: Dict[str, Any], item_id: str) -> bool:
    result = _extract_general_interaction_result(turn_summary)
    for item in _safe_list(result.get("taken_items")):
        if _safe_str(_safe_dict(item).get("item_id")) == item_id:
            return True
    return False