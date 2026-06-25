from __future__ import annotations


def test_last10_report_jobs_execute_inline_on_submit() -> None:
    import app.jobs
    from app.jobs import RPG_LAST10_REPORT_JOB_TYPE, inline_feature_jobs

    assert app.jobs is not None
    assert RPG_LAST10_REPORT_JOB_TYPE in inline_feature_jobs.INLINE_FEATURE_JOB_TYPES
    assert RPG_LAST10_REPORT_JOB_TYPE not in inline_feature_jobs.BACKGROUND_INLINE_FEATURE_JOB_TYPES
