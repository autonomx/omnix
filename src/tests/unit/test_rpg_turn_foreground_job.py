"""Regression coverage for foreground RPG player turns."""

import os
import sys

# Match the lightweight path setup used by the existing unit tests.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def test_rpg_turn_jobs_are_not_background_inline_jobs():
    import app.jobs.inline_feature_jobs as inline_feature_jobs

    assert "rpg.turn" in inline_feature_jobs.INLINE_FEATURE_JOB_TYPES
    assert "rpg.turn" not in inline_feature_jobs.BACKGROUND_INLINE_FEATURE_JOB_TYPES
    assert inline_feature_jobs.RPG_LAST10_REPORT_JOB_TYPE in inline_feature_jobs.BACKGROUND_INLINE_FEATURE_JOB_TYPES


def test_foreground_rpg_turn_visible_text_has_fallback_text():
    import app.jobs  # noqa: F401
    import app.jobs.inline_feature_jobs as inline_feature_jobs

    result = {"player_input": "I ask Bran how he is doing"}
    visible = inline_feature_jobs._rpg_turn_visible_text(result)

    assert visible
    assert "I ask Bran how he is doing" in visible
    assert "accepted" in visible.lower()


def test_foreground_social_turn_bypasses_provider_runtime():
    import app.jobs  # noqa: F401
    import app.jobs.inline_feature_jobs as inline_feature_jobs

    result = inline_feature_jobs._apply_authoritative_rpg_turn(
        "missing-session-is-ok-for-fast-social-turn",
        "i ask bran how he is",
    )

    assert result is not None
    assert result["ok"] is True
    assert result["foreground_fast_turn"] is True
    assert result["llm_called"] is False
    assert "Bran" in result["final_narration"]
