from tests.rpg.autoplay_llm_campaign import _scan_for_grounding_validation


def test_scan_for_grounding_validation_finds_deep_artifact():
    row = {
        "turn": 1,
        "result": {
            "deferred_narration": {
                "narration_json": {
                    "grounding_validation": {
                        "ok": True,
                        "selected_candidate": "primary",
                        "fallback_used": False,
                    }
                }
            }
        },
    }

    grounding = _scan_for_grounding_validation(row)

    assert grounding["ok"] is True
    assert grounding["selected_candidate"] == "primary"