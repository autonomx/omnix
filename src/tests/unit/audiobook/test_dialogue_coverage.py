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
