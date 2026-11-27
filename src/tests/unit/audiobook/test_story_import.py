"""A story handed over from Storyteller: its source and its speakers (Storyteller roadmap ST-4.4)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.apps.audiobook.annotation import Speaker, SpeakerAlias
from app.apps.audiobook.models import SourceSpan
from app.apps.audiobook.spans import DETECTOR_VERSION, UnicodeDialogueDetector
from app.apps.audiobook.story_import import (
    StoryImport,
    StoryLineMatcher,
    story_annotations,
    story_markdown,
    story_speaker_lines,
)

MARA = "00000000-0000-4000-8000-00000000000a"
TOMAS = "00000000-0000-4000-8000-00000000000b"
SPEAKERS = [Speaker(MARA, "Mara"), Speaker(TOMAS, "Tomas")]
ALIASES = [SpeakerAlias("the captain", MARA, "confirmed"), SpeakerAlias("Tom", TOMAS, "proposed")]


def story(*chapters: list[dict], cast: list[dict] | None = None) -> StoryImport:
    return StoryImport.model_validate({
        "title": "The Tide",
        "story_project_id": "story-1",
        "chapters": [{"title": f"Part {number}", "blocks": blocks} for number, blocks in enumerate(chapters, start=1)],
        "cast": cast or [{"name": "Mara", "aliases": ["the captain"]}, {"name": "Tomas"}],
    })


def span(index: int, text: str, kind: str = "dialogue") -> SourceSpan:
    return SourceSpan(f"span-{index}", "chapter-1", index, 0, len(text), text, "0" * 64, kind, DETECTOR_VERSION)


def test_the_source_is_a_heading_per_chapter_and_a_paragraph_per_block():
    handed = story(
        [{"text": "The tide went out.\n\nGulls cried."},
         {"kind": "dialogue", "text": "“Who goes there?”", "speaker": "Mara"}],
        [{"text": "# Not a heading"}, {"text": "   "}],
    )
    assert story_markdown(handed) == (
        "# Part 1\n\nThe tide went out. Gulls cried.\n\n“Who goes there?”\n\n# Part 2\n\nNot a heading\n"
    )
    assert story_speaker_lines(handed) == [{"text": "“Who goes there?”", "speaker": "Mara", "unverified": False}]


def test_a_paragraph_that_reads_as_a_chapter_heading_stays_in_its_chapter():
    from app.apps.audiobook.extraction import extract_source

    handed = story([{"text": "She ran."}, {"text": "Chapter 3 of her life began at dawn."},
                    {"text": "Dusk."}, {"text": "Chapter two was the hardest."}])
    assert story_markdown(handed) == (
        "# Part 1\n\nShe ran. Chapter 3 of her life began at dawn.\n\nDusk. Chapter two was the hardest.\n"
    )
    revision = extract_source(project_id="book-1", content=story_markdown(handed).encode("utf-8"),
                              source_format="md")
    assert [chapter.title for chapter in revision.chapters] == ["Part 1"]


def test_a_story_without_text_or_past_its_bounds_is_refused():
    with pytest.raises(ValidationError, match="no text"):
        story([{"text": "  "}])
    with pytest.raises(ValidationError):
        StoryImport.model_validate({"title": "", "story_project_id": "s", "chapters": [{"blocks": []}]})


def test_the_story_source_reads_as_dialogue_where_the_story_has_spoken_lines():
    text = story_markdown(story([
        {"text": "Dusk fell."},
        {"kind": "dialogue", "text": "“Who goes there?”", "speaker": "Mara"},
    ])).split("\n\n", 1)[1]
    spans = UnicodeDialogueDetector().detect("chapter-1", text)
    assert [(item.structural_kind, item.source_text.strip()) for item in spans if item.source_text.strip()] == [
        ("narration", "Dusk fell."), ("dialogue", "“Who goes there?”"),
    ]


def test_spans_match_the_story_lines_in_order():
    matcher = StoryLineMatcher([
        {"text": "“Yes.” “Now.”", "speaker": "Mara"},
        {"text": "“Yes.”", "speaker": "Tomas"},
        {"text": "“Run!”", "speaker": "Tomas"},
    ])
    # Two quotations of one line, then the same short line said by the next speaker.
    assert [(line or {}).get("speaker") for line in map(matcher.match, ["“Yes.”", "“Now.”", "“yes”"])] == [
        "Mara", "Mara", "Tomas",
    ]
    assert matcher.match("“Never said.”") is None
    assert matcher.match("…") is None
    assert matcher.match("“Run!”")["speaker"] == "Tomas"


def test_a_stray_word_does_not_jump_to_a_later_line_that_contains_it():
    matcher = StoryLineMatcher([
        {"text": "“Hold fast.”", "speaker": "Mara"},
        {"text": "“Aye.”", "speaker": "Tomas"},
        {"text": "“No, never.”", "speaker": "Mara"},
        {"text": "“Then go, and say no more.”", "speaker": "Tomas"},
    ])
    assert matcher.match("“Hold fast.”")["speaker"] == "Mara"
    # A quotation the story kept as narration: not the next line, and only a word of a later one.
    assert matcher.match("“no”") is None
    assert matcher.match("“more”") is None
    assert [matcher.match(text)["speaker"] for text in ("“Aye.”", "“No, never.”", "“Then go,", "and say no more.”")] \
        == ["Tomas", "Mara", "Tomas", "Tomas"]


def test_the_story_gives_the_speakers_its_cast_knows_and_leaves_the_rest_to_the_classifier():
    matcher = StoryLineMatcher([
        {"text": "“Hold fast.”", "speaker": "the captain"},
        {"text": "“Aye.”", "speaker": "Tom"},
        {"text": "“Who are you?”", "speaker": "Stranger", "unverified": True},
        {"text": "“Ho!”", "speaker": "Tomas"},
    ])
    spans = [span(0, "“Hold fast.”"), span(1, "She turned.", "narration"), span(2, "“Aye.”"),
             span(3, "“Who are you?”"), span(4, "“Ho!”"), span(5, "“Unwritten.”")]
    given = story_annotations(spans, matcher, speakers=SPEAKERS, aliases=ALIASES, dialogue_target_ids=None)
    # A confirmed alias counts; a proposed one, an unverified speaker and a line the story lacks don't.
    assert {span_id: annotation.speaker_id for span_id, annotation in given.items()} == {
        "span-0": MARA, "span-4": TOMAS,
    }
    assert given["span-0"].role == "dialogue" and given["span-0"].review_reason is None
    assert given["span-0"].evidence["speaker_source"] == "story"


def test_a_span_outside_the_analysis_targets_is_not_attributed():
    matcher = StoryLineMatcher([{"text": "“Hold fast.”", "speaker": "Mara"}])
    assert story_annotations([span(0, "“Hold fast.”")], matcher, speakers=SPEAKERS, aliases=ALIASES,
                             dialogue_target_ids=set()) == {}
