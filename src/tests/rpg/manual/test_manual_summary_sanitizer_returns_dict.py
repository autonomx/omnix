from tests.rpg.manual.summary_sanitizer import sanitize_turn_for_summary


def test_summary_sanitizer_returns_dict_for_plain_turn():
    result = sanitize_turn_for_summary(
        {
            "turn_index": 1,
            "player": "I inspect the objective.",
            "result": {"ok": True},
        }
    )

    assert isinstance(result, dict)
    assert result.get("turn_index") == 1


def test_summary_sanitizer_returns_dict_for_m46_only_turn():
    result = sanitize_turn_for_summary(
        {
            "turn_index": 1,
            "player": "I inspect the objective.",
            "story_arc_milestones_m46_m48_check_results": [
                {
                    "check_type": "story_objective_projection",
                    "ok": True,
                    "projection": {"active_objectives": []},
                }
            ],
        }
    )

    assert isinstance(result, dict)
    assert result["story_arc_milestones_m46_m48_check_results"][0]["ok"] is True


def test_summary_sanitizer_returns_dict_for_m43_only_turn():
    result = sanitize_turn_for_summary(
        {
            "turn_index": 1,
            "player": "I inspect activation.",
            "story_pack_activation_m43_m45_check_results": [
                {
                    "check_type": "story_pack_activation_status",
                    "ok": True,
                    "actual_active": False,
                }
            ],
        }
    )

    assert isinstance(result, dict)
    assert result["story_pack_activation_m43_m45_check_results"][0]["ok"] is True