from __future__ import annotations

from app.rpg.narration_quality import (
    NarrationQualityPolicy,
    build_safe_rewrite_contract,
    evaluate_narration_quality,
)


def test_narration_quality_flags_repeated_phrases_and_slop() -> None:
    report = evaluate_narration_quality(
        "The air is thick with smoke. The air is thick with smoke. The air is thick with smoke."
    )

    assert report.should_request_rewrite is True
    assert "slop_phrase" in report.rewrite_reasons
    assert "repeated_ngram" in report.rewrite_reasons
    assert "the air is thick with" in report.slop_phrase_hits


def test_narration_quality_clean_text_does_not_request_rewrite() -> None:
    report = evaluate_narration_quality(
        "Bran counts five silver into the till and slides a brass room key across the counter."
    )

    assert report.should_request_rewrite is False
    assert report.rewrite_reasons == ()
    assert report.issues == ()


def test_narration_quality_recent_overlap_is_reported() -> None:
    recent = ["Bran counts five silver into the till and slides a brass room key across the counter."]
    report = evaluate_narration_quality(
        "Bran counts five silver into the till and slides a brass room key across the counter.",
        recent_texts=recent,
        policy=NarrationQualityPolicy(recent_overlap_ratio_limit=0.1),
    )

    assert report.should_request_rewrite is True
    assert "recent_overlap" in report.rewrite_reasons
    assert report.recent_overlap_ratio > 0.1


def test_safe_rewrite_contract_preserves_state_facts_and_limits_scope() -> None:
    state_facts = {
        "location": "Rusty Flagon Tavern",
        "currency_delta": "-5 silver",
        "inventory_delta": "+room_key_rusty_flagon",
    }
    report = evaluate_narration_quality("Only time will tell. Only time will tell.")
    contract = build_safe_rewrite_contract(
        "Only time will tell. Only time will tell.",
        state_facts=state_facts,
        quality_report=report,
    )

    assert contract["task"] == "presentation_rewrite_only"
    assert contract["rewrite_requested"] is True
    assert contract["state_facts"] == state_facts
    rules = "\n".join(contract["rules"])
    assert "Do not add inventory" in rules
    assert "Return only the rewritten narration text." in rules
