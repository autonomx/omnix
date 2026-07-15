from __future__ import annotations

from datetime import timedelta

from app.desktop_companion.commentary import (
    CompanionCommentaryLedger,
    build_commentary_candidate,
    commentary_similarity,
    desktop_commentary_prompt,
)
from app.desktop_companion.models import (
    CompanionAttentionDecision,
    DesktopObservation,
    DesktopObservedChange,
    DesktopObservedValue,
    utcnow,
)


def observation() -> DesktopObservation:
    now = utcnow()
    return DesktopObservation(
        observation_id="obs-comment",
        session_id="chat-1",
        capture_generation="capture-1",
        source_fingerprint="screen-1",
        client_sequence=1,
        captured_at=now,
        observed_at=now,
        expires_at=now + timedelta(seconds=12),
        change_kind="scene_change",
        current_scene=DesktopObservedValue(value="A game inventory menu", confidence=0.9),
        visible_changes=[
            DesktopObservedChange(
                event="The inventory menu opened",
                confidence=0.88,
                fingerprint="change:inventory",
            )
        ],
        uncertainties=["The selected item is unclear"],
        importance=0.7,
    )


def decision(**updates) -> CompanionAttentionDecision:
    values = {
        "reaction": "glance",
        "should_generate": True,
        "should_deliver": True,
        "target_sentences": 1,
        "priority": "normal",
        "rationale": "scene_change",
    }
    values.update(updates)
    return CompanionAttentionDecision(**values)


def test_commentary_prompt_requires_specific_grounding_or_skip():
    prompt = desktop_commentary_prompt(observation(), decision())
    assert "output exactly SKIP" in prompt
    assert "untrusted observed content" in prompt
    assert "obs-comment" in prompt


def test_skip_and_duplicate_outputs_do_not_become_deliverable_comments():
    skipped = build_commentary_candidate(
        "SKIP",
        observation=observation(),
        decision=decision(),
    )
    duplicate = build_commentary_candidate(
        "That inventory menu opened quickly.",
        observation=observation(),
        decision=decision(),
        recent_comments=("The inventory menu opened quickly.",),
    )

    assert skipped.action == "skip"
    assert skipped.skip_reason == "model_skip"
    assert duplicate.action == "skip"
    assert duplicate.skip_reason == "duplicate_commentary"


def test_lexical_similarity_catches_close_paraphrases():
    score = commentary_similarity(
        "That inventory menu opened quickly",
        "The inventory menu opened really quickly",
    )
    assert score >= 0.65


def test_ledger_is_bounded_and_tracks_only_delivered_text_for_dedupe():
    ledger = CompanionCommentaryLedger(maximum_entries_per_session=2)
    first = build_commentary_candidate(
        "The inventory is finally open.",
        observation=observation(),
        decision=decision(),
    )
    second = build_commentary_candidate(
        "That item grid is packed.",
        observation=observation(),
        decision=decision(),
    )
    third = build_commentary_candidate(
        "The selected slot is hard to read.",
        observation=observation(),
        decision=decision(should_deliver=False),
    )
    ledger.record(first, status="completed", delivered_at=utcnow())
    ledger.record(second, status="interrupted", delivered_at=utcnow(), interrupted_at_phrase=1)
    ledger.record(third, status="generated")

    assert len(ledger.recent("chat-1", limit=10)) == 2
    assert ledger.recent_delivered_text("chat-1") == ("That item grid is packed.",)
