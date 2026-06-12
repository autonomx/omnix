from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

NEXT_ACTION_BUTTONS_VERSION = "rpg_next_action_buttons_v1"
NEXT_ACTION_BUTTONS_SUMMARY_VERSION = "rpg_next_action_buttons_summary_v1"


def _d(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _l(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _clip(value: Any, limit: int = 220) -> str:
    return _s(value).strip()[:limit]


def _duplicate_ids(items: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for item in items:
        item_id = _clip(item.get("id"), 90)
        if not item_id:
            continue
        if item_id in seen:
            dupes.add(item_id)
        seen.add(item_id)
    return sorted(dupes)


def build_next_action_buttons(contract: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project a player-agency contract into UI-button metadata.

    Buttons are presentation only. Clicking a button must submit the preserved
    canonical command back through normal runtime validation.
    """

    contract = _d(contract)
    options = _l(contract.get("options"))
    buttons: list[dict[str, Any]] = []
    seen: set[str] = set()
    warnings: list[str] = []
    for index, raw_option in enumerate(options, start=1):
        option = _d(raw_option)
        option_id = _clip(option.get("id"), 90) or f"option-{index}"
        if option_id in seen:
            warnings.append(f"duplicate_option_id:{option_id}")
            continue
        seen.add(option_id)
        command = _clip(option.get("command"), 260)
        if not command:
            warnings.append(f"empty_command:{option_id}")
            continue
        label = _clip(option.get("label"), 90) or command
        description = _clip(option.get("description"), 260)
        button = {
            "id": option_id,
            "label": label,
            "description": description,
            "submit_command": command,
            "command": command,
            "action_type": _clip(option.get("action_type"), 80),
            "target_id": _clip(option.get("target_id"), 80),
            "target_name": _clip(option.get("target_name"), 80),
            "tone_tags": [_clip(tag, 32).lower().replace(" ", "_") for tag in _l(option.get("tone_tags"))[:8] if _clip(tag, 32)],
            "validation_required": True,
            "presentation_only": True,
            "source_option": deepcopy(option),
        }
        buttons.append(button)
    return {
        "format_version": NEXT_ACTION_BUTTONS_VERSION,
        "button_count": len(buttons),
        "buttons": buttons,
        "warnings": sorted(set(warnings))[:50],
        "safety": {
            "click_submits_command": True,
            "runtime_validation_required": True,
            "label_is_presentation_only": True,
            "freeform_input_remains_primary": True,
        },
    }


def summarize_next_action_buttons(button_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return deterministic report-facing counts for next-action button payloads."""

    payload = _d(button_payload)
    buttons = [_d(item) for item in _l(payload.get("buttons")) if _d(item)]
    empty_submit_commands = [
        _clip(button.get("id"), 90) or f"button-{index}"
        for index, button in enumerate(buttons, start=1)
        if not _clip(button.get("submit_command") or button.get("command"), 260)
    ]
    invalid_flags = [
        _clip(button.get("id"), 90) or f"button-{index}"
        for index, button in enumerate(buttons, start=1)
        if button.get("validation_required") is not True or button.get("presentation_only") is not True
    ]
    tone_tags = sorted({tag for button in buttons for tag in [_clip(item, 32) for item in _l(button.get("tone_tags"))] if tag})
    return {
        "format_version": NEXT_ACTION_BUTTONS_SUMMARY_VERSION,
        "button_count": len(buttons),
        "button_ids": [_clip(button.get("id"), 90) for button in buttons if _clip(button.get("id"), 90)],
        "duplicate_button_ids": _duplicate_ids(buttons),
        "empty_submit_commands": empty_submit_commands,
        "invalid_validation_or_presentation_flags": invalid_flags,
        "tone_tags": tone_tags[:16],
        "ok": not empty_submit_commands and not invalid_flags and not _duplicate_ids(buttons),
    }


def attach_next_action_buttons(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result
    contract = _d(result.get("next_actions") or result.get("player_agency_contract"))
    if not contract:
        nested = _d(result.get("result"))
        contract = _d(nested.get("next_actions") or nested.get("player_agency_contract"))
    buttons = build_next_action_buttons(contract)
    result["next_action_buttons"] = deepcopy(buttons)
    nested = _d(result.get("result"))
    if nested:
        nested["next_action_buttons"] = deepcopy(buttons)
        result["result"] = nested
    return result
