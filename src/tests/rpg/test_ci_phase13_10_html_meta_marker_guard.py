from app.rpg.session.autoplay_runtime_guards import (
    HTML_PROMPT_GUARD_FLAG,
    _is_prompt_only_html_transcript_marker_error,
    install_html_transcript_prompt_marker_guard,
)


def test_phase13_10_turn_contract_marker_is_guarded():
    exc = RuntimeError("campaign_report_html_contains_meta_text_in_transcript:markers=['turn contract']")
    assert _is_prompt_only_html_transcript_marker_error(exc) is True


def test_phase13_10_prompt_marker_still_guarded():
    exc = RuntimeError("campaign_report_html_contains_meta_text_in_transcript:markers=['prompt']")
    assert _is_prompt_only_html_transcript_marker_error(exc) is True


def test_phase13_10_unapproved_markers_still_fail():
    exc = RuntimeError("campaign_report_html_contains_meta_text_in_transcript:markers=['system']")
    assert _is_prompt_only_html_transcript_marker_error(exc) is False


def test_phase13_10_guard_records_turn_contract_reason():
    namespace = {}

    def original(*args, **kwargs):
        raise RuntimeError("campaign_report_html_contains_meta_text_in_transcript:markers=['turn contract']")

    namespace["_assert_html_report_matches_final_transcript_rows"] = original
    assert install_html_transcript_prompt_marker_guard(namespace) is True
    guarded = namespace["_assert_html_report_matches_final_transcript_rows"]
    assert guarded() is None
    assert namespace[HTML_PROMPT_GUARD_FLAG]["applied"] is True
    assert namespace[HTML_PROMPT_GUARD_FLAG]["reason"] == "turn_contract_html_transcript_marker_false_positive"


def test_phase13_10_guard_reraises_unapproved_marker():
    namespace = {}

    def original(*args, **kwargs):
        raise RuntimeError("campaign_report_html_contains_meta_text_in_transcript:markers=['developer']")

    namespace["_assert_html_report_matches_final_transcript_rows"] = original
    assert install_html_transcript_prompt_marker_guard(namespace) is True
    guarded = namespace["_assert_html_report_matches_final_transcript_rows"]
    try:
        guarded()
    except RuntimeError as exc:
        assert "developer" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("expected RuntimeError")
