from __future__ import annotations

import pytest

from app.apps.audiobook import performance_direction as direction
from app.apps.audiobook.performance import normalize_performance, render_generation_parameters, speaker_levels
from app.providers.fish_s2_pro_provider import with_direction

ANGRY = "11111111-1111-1111-1111-111111111111"
CALM = "22222222-2222-2222-2222-222222222222"


# -- Fish: the delivery note becomes an inline tag ---------------------------

@pytest.mark.parametrize("note,expected", [
    ("angry, shouting", "[angry, shouting] Get out."),
    ("  [whispering]  afraid. ", "[whispering afraid] Get out."),
    ("", "Get out."),
    (None, "Get out."),
])
def test_a_delivery_note_leads_the_line_as_an_s2_tag(note, expected):
    assert with_direction("Get out.", note) == expected


# -- book and character performance ------------------------------------------

def test_the_default_performance_adds_nothing():
    assert normalize_performance(None) == {"stability": 0.75, "style": 0.35, "speakers": {}}
    assert render_generation_parameters("fish-s2-pro", None, {"max_new_tokens": 9}) == ({"max_new_tokens": 9}, {})


def test_book_levels_apply_to_everyone_and_a_character_overrides_them():
    performance = {"stability": 0.5, "style": 0.35,
                   "speakers": {ANGRY: {"stability": 0.0, "style": 1.0}, CALM: {"stability": 0.75}}}

    book, speakers = render_generation_parameters("fish-s2-pro", performance)

    assert book == {"temperature": 0.8}
    assert speakers[ANGRY] == {"temperature": 1.0, "top_p": 0.95}
    # Back at the default position: the engine default, not the book's change.
    assert speakers[CALM] == {}
    assert speaker_levels(performance, "someone-else") == {"stability": 0.5, "style": 0.35}


def test_a_character_matching_the_book_needs_no_parameters_of_its_own():
    performance = {"stability": 0.5, "speakers": {ANGRY: {"stability": 0.5}}}

    assert render_generation_parameters("fish-s2-pro", performance)[1] == {}


@pytest.mark.parametrize("bad", [{"stability": 1.5}, {"style": "loud"}, {"speakers": {ANGRY: "calm"}}])
def test_invalid_performance_is_rejected(bad):
    with pytest.raises(ValueError):
        normalize_performance(bad)


# -- the performance director ------------------------------------------------

@pytest.mark.parametrize("raw,clean", [
    ("Angry, SHOUTING", "angry, shouting"),
    ("[whispering; afraid]", "whispering, afraid"),
    ("neutral", ""),
    ("\"sarcastic\".", "sarcastic"),
    ("very very very very very very slow and deliberate tone indeed", "very very very very very very slow and"),
    (None, ""),
])
def test_directions_are_cleaned_to_short_safe_notes(raw, clean):
    assert direction.clean_direction(raw) == clean


def _line(span_id: str, start: int, end: int, speaker: str = "Ann") -> dict:
    return {"id": span_id, "start_offset": start, "end_offset": end, "speaker": speaker}


def test_windows_mark_each_target_line_with_its_speaker():
    text = 'She turned. "Get out!" He laughed. "Make me."'
    lines = [_line("s1", 12, 22, "Ann"), _line("s2", 35, 45, "Bob")]

    (story, span_ids), = direction.direction_windows(text, lines)

    assert span_ids == ["s1", "s2"]
    assert story == 'She turned. ⟦LINE s1 | Ann⟧"Get out!" He laughed. ⟦LINE s2 | Bob⟧"Make me."'


def test_long_chapters_are_split_into_bounded_windows(monkeypatch):
    monkeypatch.setattr(direction, "_WINDOW_SPANS", 2)
    text = "x" * 100
    lines = [_line(f"s{index}", index * 10, index * 10 + 5) for index in range(5)]

    windows = direction.direction_windows(text, lines)

    assert [ids for _story, ids in windows] == [["s0", "s1"], ["s2", "s3"], ["s4"]]


def test_only_requested_spans_are_kept_from_the_answer():
    answer = {"directions": [{"span_id": "s1", "delivery": "Angry"}, {"span_id": "intruder", "delivery": "x"},
                             {"span_id": "s2", "delivery": ""}]}

    assert direction.parse_directions(answer, ["s1", "s2"]) == {"s1": "angry", "s2": ""}
    with pytest.raises(ValueError):
        direction.parse_directions({"spans": []}, ["s1"])


def test_a_chapter_is_directed_and_a_bad_answer_is_retried_once():
    chapter = {"title": "One", "canonical_text": 'He said "Hi." She said "Bye."', "spans": [
        {"id": "n1", "start_offset": 0, "end_offset": 8, "annotation": {"role": "narration"}},
        {"id": "d1", "start_offset": 8, "end_offset": 13, "annotation": {"role": "dialogue", "speaker_id": "a"}},
        {"id": "d2", "start_offset": 23, "end_offset": 29, "annotation": {"role": "dialogue", "speaker_id": "b"}},
    ]}
    requests = []

    def director(request):
        requests.append(request)
        if len(requests) == 1:
            return {"oops": True}
        return {"directions": [{"span_id": "d1", "delivery": "warm"}, {"span_id": "d2", "delivery": "cold"}]}

    directions, failures = direction.direct_chapter(director, chapter, {"a": "Ann", "b": "Bob"})

    assert directions == {"d1": "warm", "d2": "cold"}
    assert failures == []
    assert requests[1]["target_span_ids"] == ["d1", "d2"]
    assert "⟦LINE d1 | Ann⟧" in requests[1]["story_text"] and "n1" not in requests[1]["target_span_ids"]
