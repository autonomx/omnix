from __future__ import annotations

import pytest

from app.audiobook.annotation import (
    Speaker, SpeakerAlias, annotate_span_batches, annotate_spans, narrator_id,
    normalize_speaker_name, proposed_speaker_id, resolve_speaker,
)
from app.audiobook.extraction import extract_source


def _spans():
    revision = extract_source(project_id="book:1", content=b'"Hello," said Nita.\nMore text.', source_format="txt")
    return revision.chapters[0].spans


def test_proposed_speaker_id_is_stable_across_whitespace_and_case() -> None:
    assert proposed_speaker_id("book:1", "  Time   Traveller ") == proposed_speaker_id(
        "book:1", "time traveller",
    )
    assert proposed_speaker_id("book:1", "Time Traveller") != proposed_speaker_id(
        "book:2", "Time Traveller",
    )


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



def test_speaker_normalization_collapses_unicode_case_and_whitespace() -> None:
    assert normalize_speaker_name("  Time   Traveller ") == "time traveller"
    assert normalize_speaker_name("Ｎｉｔａ") == "nita"


def test_proposed_speaker_is_context_only_until_confirmed() -> None:
    proposed = Speaker("candidate-id", "Nita", status="proposed")
    assert resolve_speaker("Nita", [proposed], []) is None
    assert resolve_speaker("candidate-id", [proposed], []) is None


def test_low_confidence_known_speaker_is_routed_to_review() -> None:
    span = _spans()[0]

    def classifier(context):
        return {
            "span_id": context["span_id"],
            "speaker": "Nita",
            "role": "dialogue",
            "delivery": "quiet",
            "confidence": 0.61,
        }

    annotation = annotate_spans(
        project_id="book:1",
        spans=[span],
        speakers=[Speaker("nita-id", "Nita")],
        classifier=classifier,
    )[0]
    assert annotation.speaker_id == "nita-id"
    assert annotation.review_reason == "LOW_CONFIDENCE_SPEAKER"
    assert annotation.confidence == pytest.approx(0.61)


def test_extended_dialogue_tag_can_contradict_classifier() -> None:
    revision = extract_source(
        project_id="book:tags",
        content=b'"Run!" Daniel shouted.\n',
        source_format="txt",
    )
    spans = revision.chapters[0].spans

    def classifier(context):
        span = next(item for item in spans if item.id == context["span_id"])
        return {
            "span_id": context["span_id"],
            "speaker": "Jo" if span.structural_kind == "dialogue" else "Narrator",
            "role": span.structural_kind,
            "delivery": "urgent" if span.structural_kind == "dialogue" else "",
            "confidence": 0.99,
        }

    annotations = annotate_spans(
        project_id="book:tags",
        spans=spans,
        speakers=[Speaker("daniel-id", "Daniel"), Speaker("jo-id", "Jo")],
        classifier=classifier,
        context_window=1,
    )
    dialogue = next(item for item in annotations if item.role == "dialogue")
    assert dialogue.review_reason == "ATTRIBUTION_CONTRADICTION"


def test_batch_analysis_rolls_new_character_into_later_batches() -> None:
    revision = extract_source(
        project_id="book:rolling",
        content=b'"Hello," said Nita.\n"Again," Nita replied.\n',
        source_format="txt",
    )
    spans = revision.chapters[0].spans
    calls = []

    def classifier(context):
        calls.append(context)
        roster_names = {
            item["name"]: item["status"] for item in context["speaker_roster"]
        }
        if len(calls) == 1:
            characters = [{
                "name": "Nita",
                "aliases": ["Ms. Nita"],
                "role": "supporting",
                "traits": ["quick-witted", "skeptical"],
                "estimated_age": "20s",
                "gender_presentation": "female",
            }]
        else:
            assert roster_names.get("Nita") == "proposed"
            characters = [{"name": "Nita", "aliases": []}]
        return {
            "characters": characters,
            "spans": [
                {
                    "span_id": item["span_id"],
                    "speaker": "Nita" if item["structural_kind"] == "dialogue" else "Narrator",
                    "role": item["structural_kind"],
                    "delivery": "",
                    "confidence": 0.98,
                }
                for item in context["spans"]
            ],
        }

    result = annotate_span_batches(
        project_id="book:rolling",
        spans=spans,
        speakers=[],
        classifier=classifier,
        batch_size=1,
        context_window=1,
    )
    assert len(calls) == 2
    assert len(result.annotations) == len(spans)
    assert len(result.discovered_speakers) == 1
    assert result.discovered_speakers[0].canonical_name == "Nita"
    assert result.discovered_speakers[0].aliases == ("Ms. Nita",)
    assert result.discovered_speakers[0].role == "supporting"
    assert result.discovered_speakers[0].traits == ("quick-witted", "skeptical")
    assert result.discovered_speakers[0].estimated_age == "20s"
    assert result.discovered_speakers[0].gender_presentation == "female"
    dialogue = [item for item in result.annotations if item.role == "dialogue"]
    assert dialogue
    assert all(item.review_reason == "UNSUPPORTED_SPEAKER" for item in dialogue)



def test_batch_analysis_does_not_call_model_for_narration_only() -> None:
    revision = extract_source(
        project_id="book:narration",
        content=b"The room was quiet.\nThe lantern dimmed.\n",
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context)
        raise AssertionError("narration should not require model inference")

    result = annotate_span_batches(
        project_id="book:narration",
        spans=revision.chapters[0].spans,
        speakers=[],
        classifier=classifier,
    )
    assert calls == []
    assert all(item.role == "narration" for item in result.annotations)
    assert all(item.speaker_id == narrator_id("book:narration") for item in result.annotations)
    assert all(item.review_reason is None for item in result.annotations)


def test_proposed_speaker_id_from_classifier_is_kept_as_canonical_candidate() -> None:
    project_id = "book:provisional-id"
    revision = extract_source(
        project_id=project_id,
        content=b'"Hello."\n',
        source_format="txt",
    )
    provisional = Speaker(
        proposed_speaker_id(project_id, "Nita"),
        "Nita",
        status="proposed",
    )

    def classifier(context):
        return {
            "characters": [],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": provisional.id,
                "role": "dialogue",
                "delivery": "",
                "confidence": 0.99,
            }],
        }

    result = annotate_span_batches(
        project_id=project_id,
        spans=revision.chapters[0].spans,
        speakers=[provisional],
        classifier=classifier,
        batch_size=1,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert dialogue.speaker_id == narrator_id(project_id)
    assert dialogue.speaker_candidate == "Nita"
    assert dialogue.review_reason == "UNSUPPORTED_SPEAKER"



def test_dialogue_assigned_to_narrator_requires_review() -> None:
    span = _spans()[0]

    def classifier(context):
        return {
            "span_id": context["span_id"],
            "speaker": "Narrator",
            "role": "dialogue",
            "delivery": "",
            "confidence": 0.99,
        }

    annotation = annotate_spans(
        project_id="book:1",
        spans=[span],
        speakers=[Speaker(narrator_id("book:1"), "Narrator", "narrator")],
        classifier=classifier,
    )[0]
    assert annotation.speaker_id == narrator_id("book:1")
    assert annotation.review_reason == "NARRATOR_DIALOGUE_UNCERTAIN"



def test_multi_span_legacy_classifier_falls_back_to_per_dialogue_calls() -> None:
    revision = extract_source(
        project_id="book:legacy-batch",
        content=b'"One."\n"Two."\n',
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context)
        if "span_ids" in context:
            # A legacy integration may ignore the batch shape and return one old
            # single-span object. Omnix must detect that and retry each dialogue.
            return {
                "span_id": context["span_ids"][0],
                "speaker": "Nita",
                "role": "dialogue",
                "delivery": "",
            }
        return {
            "span_id": context["span_id"],
            "speaker": "Nita",
            "role": "dialogue",
            "delivery": "",
        }

    result = annotate_span_batches(
        project_id="book:legacy-batch",
        spans=revision.chapters[0].spans,
        speakers=[],
        classifier=classifier,
        batch_size=40,
    )
    batch_calls = [call for call in calls if "span_ids" in call]
    legacy_calls = [call for call in calls if "span_id" in call]
    assert len(batch_calls) == 1
    assert len(legacy_calls) == 2
    assert len(result.annotations) == len(revision.chapters[0].spans)
    assert all(
        item.review_reason == "UNSUPPORTED_SPEAKER"
        for item in result.annotations
        if item.role == "dialogue"
    )


def test_dialogue_batching_bounds_classifier_calls() -> None:
    revision = extract_source(
        project_id="book:batch-count",
        content=(
            '"One."\n"Two."\n"Three."\n"Four."\n"Five."\n'
        ).encode(),
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context)
        return {
            "characters": [],
            "spans": [{
                "span_id": item["span_id"],
                "speaker": "Nita",
                "role": "dialogue",
                "delivery": "",
                "confidence": 0.95,
            } for item in context["spans"]],
        }

    annotate_span_batches(
        project_id="book:batch-count",
        spans=revision.chapters[0].spans,
        speakers=[],
        classifier=classifier,
        batch_size=2,
    )
    assert len(calls) == 3
