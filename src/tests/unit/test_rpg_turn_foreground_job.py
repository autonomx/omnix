"""Regression coverage for foreground RPG player turns.

The React RPG composer submits normal player commands as ``rpg.turn`` feature
jobs. Those jobs must complete on the foreground create-job path so the submit
cycle returns a visible response instead of relying on delayed background
polling/recovery.
"""

import os
import sys

# Match the lightweight path setup used by the existing unit tests.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def test_rpg_turn_jobs_are_not_background_inline_jobs():
    import app.jobs.inline_feature_jobs as inline_feature_jobs

    assert "rpg.turn" in inline_feature_jobs.INLINE_FEATURE_JOB_TYPES
    assert "rpg.turn" not in inline_feature_jobs.BACKGROUND_INLINE_FEATURE_JOB_TYPES
    assert inline_feature_jobs.RPG_LAST10_REPORT_JOB_TYPE in inline_feature_jobs.BACKGROUND_INLINE_FEATURE_JOB_TYPES
