from __future__ import annotations

from types import ModuleType

from app.rpg.session.player_agency_buttons import build_next_action_buttons
from app.rpg.session.player_agency_runtime_hook import (
    attach_player_agency_to_runtime_result,
    force_install_player_agency_runtime_hook_for_tests,
)


def _runtime_result() -> dict:
    return {
        "ok": True,
        "npc": {"id": "npc:bran", "speaker": "Bran", "line": "Road's not kind tonight."},
        "result": {"summary": "Bran answers."},
        "simulation_state": {
            "current_location_id": "loc:rusty_flagon",
            "location_name": "Rusty Flagon",
            "player_state": {
                "personality": {"alignment": "evil", "traits": ["ruthless"]},
                "inventory_state": {"items": [{"item_id": "trail_ration", "quantity": 1}], "currency": {"silver": 10}},
            },
        },
        "runtime_state": {"current_objective": "Follow the bandit clue."},
    }


def test_attach_player_agency_to_runtime_result_adds_top_level_and_nested_next_actions() -> None:
    result = attach_player_agency_to_runtime_result(
        _runtime_result(),
        call_context={"player_input": "What can I do next?", "max_options": 5},
    )

    assert result["player_agency_runtime_hook"]["attached"] is True
    assert result["next_actions"]["format_version"] == "rpg_player_agency_contract_v1"
    assert result["next_actions"]["option_count"] >= 1
    assert result["result"]["next_actions"]["format_version"] == "rpg_player_agency_contract_v1"
    assert all(option["validation_required"] is True for option in result["next_actions"]["options"])
    assert all(option["presentation_only"] is True for option in result["next_actions"]["options"])
    assert result["next_actions"]["personality"]["tone_hint"] == "dark"


def test_next_action_button_payload_preserves_submit_commands() -> None:
    contract = {
        "format_version": "rpg_player_agency_contract_v1",
        "options": [
            {
                "id": "talk-current-npc",
                "label": "Lean on Bran until he cracks",
                "description": "A darker presentation, not a different action.",
                "command": "I ask Bran what he thinks I should do next.",
                "action_type": "social_activity",
                "target_id": "npc:bran",
                "target_name": "Bran",
                "tone_tags": ["dark", "coercive"],
                "validation_required": True,
                "presentation_only": True,
            }
        ],
    }

    buttons = build_next_action_buttons(contract)

    assert buttons["format_version"] == "rpg_next_action_buttons_v1"
    assert buttons["button_count"] == 1
    button = buttons["buttons"][0]
    assert button["label"] == "Lean on Bran until he cracks"
    assert button["submit_command"] == "I ask Bran what he thinks I should do next."
    assert button["command"] == "I ask Bran what he thinks I should do next."
    assert button["action_type"] == "social_activity"
    assert button["validation_required"] is True
    assert button["presentation_only"] is True
    assert buttons["safety"]["click_submits_command"] is True
    assert buttons["safety"]["freeform_input_remains_primary"] is True


def test_next_action_button_payload_drops_invalid_and_duplicate_buttons() -> None:
    contract = {
        "options": [
            {"id": "one", "label": "One", "command": "I inspect the area.", "action_type": "investigate"},
            {"id": "one", "label": "Duplicate", "command": "I ask again.", "action_type": "social_activity"},
            {"id": "empty", "label": "Empty", "command": "", "action_type": "observe"},
        ],
    }

    buttons = build_next_action_buttons(contract)

    assert buttons["button_count"] == 1
    assert buttons["buttons"][0]["id"] == "one"
    assert "duplicate_option_id:one" in buttons["warnings"]
    assert "empty_command:empty" in buttons["warnings"]


def test_runtime_hook_wraps_interactive_apply_turn_and_preserves_result() -> None:
    module = ModuleType("fake_interactive_runtime")
    calls: list[tuple[str, str]] = []

    def apply_turn(session_id: str, player_input: str, **kwargs):
        calls.append((session_id, player_input))
        return _runtime_result()

    module.apply_turn = apply_turn  # type: ignore[attr-defined]

    assert force_install_player_agency_runtime_hook_for_tests(module) is True
    result = module.apply_turn("session-1", "What now?", performance_override={"player_agency_max_options": 4})  # type: ignore[attr-defined]

    assert calls == [("session-1", "What now?")]
    assert result["ok"] is True
    assert result["player_agency_runtime_hook"]["attached"] is True
    assert result["player_agency_runtime_hook"]["button_payload_attached"] is True
    assert result["next_actions"]["option_count"] <= 4
    assert result["next_action_buttons"]["button_count"] == result["next_actions"]["option_count"]
    assert result["result"]["next_action_buttons"]["format_version"] == "rpg_next_action_buttons_v1"
    assert result["result"]["player_agency_runtime_hook"]["runtime_validation_required"] is True


def test_runtime_hook_is_noop_for_non_dict_results() -> None:
    module = ModuleType("fake_interactive_runtime_non_dict")

    def apply_turn(*args, **kwargs):
        return "not-a-dict"

    module.apply_turn = apply_turn  # type: ignore[attr-defined]
    assert force_install_player_agency_runtime_hook_for_tests(module) is True
    assert module.apply_turn("session-1", "What now?") == "not-a-dict"  # type: ignore[attr-defined]
