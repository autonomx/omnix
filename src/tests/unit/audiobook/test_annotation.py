from __future__ import annotations

import pytest

from app.audiobook.annotation import (
    Speaker, SpeakerAlias, annotate_spans, narrator_id, resolve_speaker,
)
from app.audiobook.extraction import extract_source


def _spans():
    revision = extract_source(project_id="book:1", content=b'"Hello," said Nita.\nMore text.', source_format="txt")
    return revision.chapters[0].spans


@pytest.mark.parametrize("result", [
    "{broken", '{"span_id": "truncated"', "", "{}", {"refusal": "cannot classify"},
    {"span_id": "wrong", "speaker": "Nita", "role": "dialogue", "delivery": ""},
    {"span_id": "x", "speaker": "Nita", "role": "dialogue", "delivery": "", "source_text": "rewritten"},
])
def test_invalid_classifier_output_preserves_every_source_span(result: object) -> None:
    spans = _spans()
    def classifier(context):
        return result
    annotations = annotate_spans(project_id="book:1", spans=spans, speakers=[], classifier=classifier)
    assert [item.span_id for item in annotations] == [span.id for span in spans]
    assert all(item.review_reason == "FALLBACK_NARRATOR" for item in annotations)
    assert all(item.speaker_id == narrator_id("book:1") for item in annotations)
    assert "".join(span.source_text for span in spans) == '"Hello," said Nita.\nMore text.'


@pytest.mark.parametrize("failure", [TimeoutError, OSError, RuntimeError])
def test_provider_failures_fall_back_without_source_loss(failure: type[Exception]) -> None:
    spans = _spans()
    def classifier(_context):
        raise failure("provider unavailable")
    annotations = annotate_spans(project_id="book:1", spans=spans, speakers=[], classifier=classifier)
    assert len(annotations) == len(spans)
    assert all(item.review_reason == "FALLBACK_NARRATOR" for item in annotations)


def test_near_names_and_possessives_do_not_silently_merge() -> None:
    nita = Speaker("nita-id", "Nita")
    father = Speaker("father-id", "Nita's father")
    speakers = [nita, father]
    assert resolve_speaker("Nita", speakers, []) == "nita-id"
    assert resolve_speaker("Nita's father", speakers, []) == "father-id"
    assert resolve_speaker("Nita Sr.", speakers, []) is None
    proposed = SpeakerAlias("Nita Sr.", "nita-id", "proposed")
    assert resolve_speaker("Nita Sr.", speakers, [proposed]) is None
    confirmed = SpeakerAlias("Nita Sr.", "nita-id", "confirmed")
    assert resolve_speaker("Nita Sr.", speakers, [confirmed]) == "nita-id"


def test_shared_surnames_and_honorifics_do_not_merge_without_confirmation() -> None:
    speakers = [Speaker("lee-id", "Ada Lee"), Speaker("doctor-id", "Dr. Lee"),
                Speaker("junior-id", "Ada Lee Jr.")]
    assert resolve_speaker("Ada Lee", speakers, []) == "lee-id"
    assert resolve_speaker("Dr. Lee", speakers, []) == "doctor-id"
    assert resolve_speaker("Ada Lee Jr.", speakers, []) == "junior-id"
    assert resolve_speaker("Lee", speakers, []) is None
    assert resolve_speaker("Ada Lee Sr.", speakers, []) is None


def test_explicit_attribution_conflict_is_reviewed() -> None:
    speakers = [Speaker("nita-id", "Nita"), Speaker("jo-id", "Jo")]
    def classifier(context):
        return {"span_id": context["span_id"], "speaker": "Jo", "role": "dialogue", "delivery": "quiet"}
    annotations = annotate_spans(project_id="book:1", spans=_spans(), speakers=speakers, classifier=classifier)
    assert any(item.review_reason == "ATTRIBUTION_CONTRADICTION" for item in annotations)
    assert any(item.review_reason == "STRUCTURE_UNCERTAIN" and item.speaker_id == narrator_id("book:1")
               for item in annotations)


def test_malformed_classification_gets_one_targeted_retry() -> None:
    calls = []

    def classifier(context):
        calls.append(context["task"])
        if len(calls) == 1:
            return "not json"
        return {"span_id": context["span_id"], "speaker": "Nita",
                "role": "dialogue", "delivery": "quiet"}

    annotations = annotate_spans(
        project_id="book:1", spans=_spans()[:1], speakers=[Speaker("nita-id", "Nita")],
        classifier=classifier,
    )
    assert calls == ["classify_only_no_source_text_in_response",
                     "retry_classification_only_no_source_text_in_response"]
    assert annotations[0].speaker_id == "nita-id"
