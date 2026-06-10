from __future__ import annotations

from app.rpg.interactive_cli_response_quality import (
    RESPONSE_QUALITY_SOURCE as APP_RESPONSE_QUALITY_SOURCE,
    apply_interactive_response_quality_cleanup as app_cleanup,
)
from rpg.interactive_cli_response_quality import (
    RESPONSE_QUALITY_SOURCE as COMPAT_RESPONSE_QUALITY_SOURCE,
    apply_interactive_response_quality_cleanup as compat_cleanup,
)


def _turn() -> dict:
    narration = "The scene shifts with the movement, carrying the pressure of the current lead into the space ahead."
    return {
        "turn_index": 1,
        "player_input": "I travel north toward the old mill.",
        "raw_narration": narration,
        "narration_preview": narration,
        "raw_result": {"narration": narration, "npc": {"speaker": "", "line": ""}},
        "extracted": {"narration": narration, "npc_speaker": "", "npc_line": ""},
        "interactive_cli_intent_diagnostics": {
            "provider_called": True,
            "final_classification": {
                "action_type": "travel",
                "target_npc": "old mill",
                "requested_terms": ["old mill", "north"],
                "service_kind": "unknown",
            },
        },
    }


def test_phase13_52_runtime_response_quality_is_app_module_available():
    assert APP_RESPONSE_QUALITY_SOURCE == "interactive_cli_response_quality_v1"
    cleaned = app_cleanup(_turn(), player_input="I travel north toward the old mill.")

    assert cleaned["interactive_cli_response_quality"]["source"] == APP_RESPONSE_QUALITY_SOURCE
    assert cleaned["interactive_cli_response_quality"]["cleanup_source"] == "travel_location_specificity"
    assert "old mill" in cleaned["raw_narration"]
    assert "north" in cleaned["raw_narration"]


def test_phase13_52_legacy_test_import_reexports_runtime_cleanup():
    assert COMPAT_RESPONSE_QUALITY_SOURCE == APP_RESPONSE_QUALITY_SOURCE
    assert compat_cleanup is app_cleanup
