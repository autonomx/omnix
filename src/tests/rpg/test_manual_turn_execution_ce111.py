from __future__ import annotations

from tests.rpg.manual import turn_execution


def test_manual_harness_prefers_interactive_first_call_runtime_wrapper():
    apply_turn = turn_execution._get_apply_turn()

    assert apply_turn.__module__ == "app.rpg.session.interactive_first_call_runtime"
    assert apply_turn.__name__ == "apply_turn"


def test_manual_harness_exposes_first_call_diagnostics_from_result():
    diagnostics = {
        "format_version": "first_call_grounding_diagnostics_v1",
        "turn_grounding_packet": {"format_version": "turn_grounding_packet_v1"},
    }
    result = {
        "first_call_semantic_advisory": {
            "first_call_grounding_diagnostics": diagnostics,
        }
    }

    assert turn_execution._extract_first_call_grounding_diagnostics(result) == diagnostics
