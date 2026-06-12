from __future__ import annotations

from tests.rpg.interactive_cli_live_agency_report import (
    aggregate_live_agency_reports,
    evaluate_live_agency_payload,
    evaluate_turn_agency_payload,
    render_live_agency_status_marker,
)


def _turn(index: int, *, command: str = "I ask Bran what to do next.", label: str = "Ask Bran", button_command: str | None = None) -> dict:
    submit = command if button_command is None else button_command
    return {
        "turn_index": index,
        "player_input": "What now?",
        "raw_result": {
            "next_actions": {
                "format_version": "rpg_player_agency_contract_v1",
                "options": [
                    {
                        "id": "talk-current-npc",
                        "action_type": "social_activity",
                        "command": command,
                        "label": label,
                        "description": "Ask the current NPC for advice.",
                        "validation_required": True,
                        "presentation_only": True,
                        "tone_tags": ["dark"] if "crack" in label.lower() else [],
                    }
                ],
            },
            "next_action_buttons": {
                "format_version": "rpg_next_action_buttons_v1",
                "buttons": [
                    {
                        "id": "talk-current-npc",
                        "label": label,
                        "description": "Ask the current NPC for advice.",
                        "submit_command": submit,
                        "command": submit,
                        "action_type": "social_activity",
                        "validation_required": True,
                        "presentation_only": True,
                        "tone_tags": ["dark"] if "crack" in label.lower() else [],
                    }
                ],
            },
        },
    }


def test_evaluate_turn_agency_payload_accepts_valid_contract_and_buttons() -> None:
    report = evaluate_turn_agency_payload(_turn(1, label="Lean on Bran until he cracks"), turn_index=1)

    assert report["ok"] is True
    assert report["option_count"] == 1
    assert report["button_count"] == 1
    assert report["option_ids"] == ["talk-current-npc"]
    assert report["button_ids"] == ["talk-current-npc"]
    assert "dark" in report["tone_tags"]
    assert report["failures"] == []


def test_evaluate_turn_agency_payload_rejects_button_command_mutation() -> None:
    report = evaluate_turn_agency_payload(
        _turn(1, command="I ask Bran what to do next.", button_command="I assassinate Bran."),
        turn_index=1,
    )

    assert report["ok"] is False
    assert "next_action_button_submit_command_mismatch" in report["failures"]
    assert report["details"]["mutated_button_commands"] == ["talk-current-npc"]


def test_evaluate_live_agency_payload_reports_coverage_and_failures() -> None:
    payload = {
        "turns": [
            _turn(1),
            {"turn_index": 2, "player_input": "What now?", "raw_result": {"next_actions": {"options": []}}},
        ]
    }

    report = evaluate_live_agency_payload(payload)

    assert report["ok"] is False
    assert report["turn_count"] == 2
    assert report["signals"]["next_action_turn_count"] == 1
    assert report["signals"]["next_action_coverage_ratio"] == 0.5
    assert "turn_2_next_actions_missing_or_empty" in report["failures"]
    assert "turn_2_next_action_buttons_missing_or_empty" in report["failures"]
    assert "next_action_coverage_ratio_below_threshold" in report["failures"]


def test_aggregate_live_agency_reports_combines_coverage() -> None:
    good = evaluate_live_agency_payload({"turns": [_turn(1), _turn(2)]})
    bad = evaluate_live_agency_payload({"turns": [_turn(1), {"turn_index": 2, "raw_result": {}}]})

    aggregate = aggregate_live_agency_reports([good, bad])

    assert aggregate["aggregate_format_version"] == "rpg_live_agency_report_aggregate_v1"
    assert aggregate["ok"] is False
    assert aggregate["passed"] == 1
    assert aggregate["failed"] == 1
    assert aggregate["total_turn_count"] == 4
    assert aggregate["signals"]["next_action_turn_count"] == 3
    assert aggregate["signals"]["next_action_coverage_ratio"] == 0.75


def test_render_live_agency_status_marker_includes_coverage() -> None:
    report = evaluate_live_agency_payload({"turns": [_turn(1)]})
    marker = render_live_agency_status_marker(report)

    assert marker.startswith("[RPG_LIVE_AGENCY_REPORT]")
    assert "ok=true" in marker
    assert "next_actions=1.000" in marker
    assert "buttons=1.000" in marker
