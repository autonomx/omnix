from __future__ import annotations

from tests.rpg.manual.scenario_execution import _n101_stabilization_gate_warnings


def test_n101_fake_debt_warning_helper_does_not_need_outer_regression_warnings():
    turn_record = {
        "narration_preview": "Bran says no. He does not owe you 50 gold.",
        "grounding_validation": {
            "ok": True,
            "selected_candidate": "primary",
            "fallback_used": False,
            "fallback_source": "",
            "violations": [],
        },
        "narration_debug": {
            "final_narration": "Bran says no. He does not owe you 50 gold.",
            "npc_line": "No. I do not owe you 50 gold.",
        },
    }

    warnings = _n101_stabilization_gate_warnings(
        scenario_name="npc_bran_refuses_fake_debt",
        turn_index=1,
        turn_record=turn_record,
    )

    assert isinstance(warnings, list)
    assert "n101_missing_grounding_validation" not in warnings