from __future__ import annotations

from app.audiobook.dialogue_coverage import audit_dialogue_coverage
from app.audiobook.hashing import text_hash
from app.audiobook.models import SourceSpan


def _narration(text: str) -> SourceSpan:
    return SourceSpan(
        id="span-one",
        chapter_id="chapter-one",
        ordinal=0,
        start_offset=0,
        end_offset=len(text),
        source_text=text,
        source_hash=text_hash(text),
        structural_kind="narration",
        detector_version="test-detector",
    )


def test_inline_quoted_term_does_not_trigger_dialogue_review() -> None:
    findings = audit_dialogue_coverage([
        _narration('He called the device "magic." and kept walking.')
    ])

    assert findings == {}


def test_line_leading_unfamiliar_quotes_still_trigger_review() -> None:
    findings = audit_dialogue_coverage([
        _narration("„You cannot be serious,“ Nita replied.\n")
    ])

    assert findings["span-one"]["signal"] == "quote_in_narration"
    assert findings["span-one"]["source_offset"] == 0


def test_speech_tag_before_unfamiliar_quote_still_triggers_review() -> None:
    text = "Nita said, „You cannot be serious.“"
    findings = audit_dialogue_coverage([_narration(text)])

    assert findings["span-one"]["signal"] == "quote_in_narration"
    assert findings["span-one"]["source_offset"] == text.index("„")


def test_long_narration_with_non_speaker_said_does_not_trigger_review() -> None:
    text = ("The brass sign said CLOSED. " + ("The corridor remained quiet. " * 90)).strip()
    assert len(text) >= 2_000

    findings = audit_dialogue_coverage([_narration(text)])

    assert findings == {}


def test_long_narration_with_named_speech_attribution_still_triggers_review() -> None:
    text = ("The corridor remained quiet. " * 80) + " Nita said the answer softly."
    assert len(text) >= 2_000

    findings = audit_dialogue_coverage([_narration(text)])

    assert findings["span-one"]["signal"] == "speech_tag_without_dialogue"


def test_masked_dialogue_does_not_suppress_visible_story_coverage() -> None:
    hidden_dialogue = SourceSpan(
        id="span-hidden",
        chapter_id="chapter-one",
        ordinal=0,
        start_offset=0,
        end_offset=12,
        source_text=" " * 12,
        source_hash=text_hash('"Hidden."\n'),
        structural_kind="dialogue",
        detector_version="test-detector",
    )
    story = (
        "The corridor remained quiet. " * 80
    ) + " Nita said the answer softly."
    visible_narration = SourceSpan(
        id="span-story",
        chapter_id="chapter-one",
        ordinal=1,
        start_offset=12,
        end_offset=12 + len(story),
        source_text=story,
        source_hash=text_hash(story),
        structural_kind="narration",
        detector_version="test-detector",
    )

    findings = audit_dialogue_coverage([hidden_dialogue, visible_narration])

    assert findings["span-story"]["signal"] == "speech_tag_without_dialogue"
