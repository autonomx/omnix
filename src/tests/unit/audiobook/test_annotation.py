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



def test_full_story_analysis_accepts_valid_payload_without_parser_error() -> None:
    revision = extract_source(
        project_id="book:batch-parser",
        content=b'"Hello," said Nita.\n',
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context["task"])
        return {
            "characters": [{
                "name": "Nita",
                "aliases": [],
                "role": "speaker",
                "traits": [],
            }],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": "Nita",
                "role": "dialogue",
                "delivery": "neutral",
                "confidence": 0.99,
            }],
        }

    result = annotate_span_batches(
        project_id="book:batch-parser",
        spans=revision.chapters[0].spans,
        speakers=[],
        classifier=classifier,
    )

    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert dialogue.review_reason is None
    assert dialogue.speaker_id == proposed_speaker_id("book:batch-parser", "Nita")
    assert dialogue.speaker_candidate == "Nita"
    assert [item.canonical_name for item in result.discovered_speakers] == ["Nita"]
    assert calls == [
        "analyze_story_dialogue_full_context",
        "verify_story_dialogue_full_context",
    ]


def test_full_story_request_identifies_contract_detector_and_marked_story() -> None:
    revision = extract_source(
        project_id="book:versioned-request",
        content=b'Nita entered.\n"Hello."\nShe waved.\n',
        source_format="txt",
    )
    calls = []
    classifier_details = {
        "provider_id": "chatgpt_codex",
        "model": "configured-gpt-5.6-sol",
        "version": "audiobook-classifier-v7",
        "reasoning_effort": "xhigh",
    }

    def classifier(context):
        calls.append(context)
        classifier_details["model"] = "gpt-5.6-sol"
        return {
            "characters": [{"name": "Nita", "aliases": []}],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": "Nita",
                "role": "dialogue",
                "delivery": "",
                "confidence": 0.99,
            }],
        }

    result = annotate_span_batches(
        project_id="book:versioned-request",
        spans=revision.chapters[0].spans,
        speakers=[],
        classifier=classifier,
        classifier_details=classifier_details,
        batch_size=1,
    )

    first = calls[0]
    assert first["analysis_contract_version"] == "audiobook-analysis-contract-v4"
    assert first["span_detector_versions"] == ["audiobook-spans-v7"]
    assert first["task"] == "analyze_story_dialogue_full_context"
    assert "Nita entered." in first["story_text"]
    assert "She waved." in first["story_text"]
    assert "<DIALOGUE" in first["story_text"]
    assert 'target="true"' in first["story_text"]
    assert "direct_attribution_candidates" not in first["spans"][0]
    assert "classifier_details" not in first
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert dialogue.evidence["classifier_provider_id"] == "chatgpt_codex"
    assert dialogue.evidence["classifier_model"] == "gpt-5.6-sol"
    assert dialogue.evidence["classifier_version"] == "audiobook-classifier-v7"
    assert dialogue.evidence["classifier_reasoning_effort"] == "xhigh"


def test_full_story_analysis_discovers_character_before_verification() -> None:
    revision = extract_source(
        project_id="book:rolling",
        content=b'"Hello," said Nita.\n"Again," Nita replied.\n',
        source_format="txt",
    )
    spans = revision.chapters[0].spans
    calls = []

    def classifier(context):
        calls.append(context)
        if context["task"] == "analyze_story_dialogue_full_context":
            assert '"Hello," said Nita.' in context["story_text"]
            assert '"Again," Nita replied.' in context["story_text"]
            characters = [{
                "name": "Nita",
                "aliases": ["Ms. Nita"],
                "role": "supporting",
                "traits": ["quick-witted", "skeptical"],
                "estimated_age": "20s",
                "gender_presentation": "female",
            }]
        else:
            assert context["task"] == "verify_story_dialogue_full_context"
            assert any(item["name"] == "Nita" for item in context["speaker_roster"])
            assert context["proposed_assignments"]
            characters = [{"name": "Nita", "aliases": ["Ms. Nita"]}]
        return {
            "characters": characters,
            "spans": [{
                "span_id": item["span_id"],
                "speaker": "Nita",
                "role": "dialogue",
                "delivery": "",
                "confidence": 0.98,
            } for item in context["spans"]],
        }

    result = annotate_span_batches(
        project_id="book:rolling",
        spans=spans,
        speakers=[],
        classifier=classifier,
        batch_size=1,
        context_window=1,
    )
    assert [call["task"] for call in calls] == [
        "analyze_story_dialogue_full_context",
        "verify_story_dialogue_full_context",
    ]
    assert len(result.annotations) == len(spans)
    assert len(result.discovered_speakers) == 1
    assert result.discovered_speakers[0].canonical_name == "Nita"
    assert result.discovered_speakers[0].aliases == ("Ms. Nita",)
    assert result.discovered_speakers[0].role == "supporting"
    assert result.discovered_speakers[0].traits == ("quick-witted", "skeptical")
    assert result.discovered_speakers[0].estimated_age == "20s"
    assert result.discovered_speakers[0].gender_presentation == "female"
    dialogue = [item for item in result.annotations if item.role == "dialogue"]
    expected_id = proposed_speaker_id("book:rolling", "Nita")
    assert dialogue
    assert all(item.speaker_id == expected_id for item in dialogue)
    assert all(item.review_reason is None for item in dialogue)


def test_verification_pass_can_correct_high_confidence_first_pass() -> None:
    revision = extract_source(
        project_id="book:verify-correction",
        content=b'Daniel faced Mara.\n"Ready?" Mara asked.\n',
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context["task"])
        speaker = (
            "Daniel"
            if context["task"] == "analyze_story_dialogue_full_context"
            else "Mara"
        )
        return {
            "characters": [
                {"name": "Daniel", "aliases": []},
                {"name": "Mara", "aliases": []},
            ],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": speaker,
                "role": "dialogue",
                "delivery": "",
                "confidence": 0.99,
            }],
        }

    result = annotate_span_batches(
        project_id="book:verify-correction",
        spans=revision.chapters[0].spans,
        speakers=[],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert dialogue.speaker_candidate == "Mara"
    assert dialogue.speaker_id == proposed_speaker_id(
        "book:verify-correction", "Mara",
    )
    assert dialogue.review_reason is None
    assert dialogue.evidence["verification_changed"] is True
    assert dialogue.evidence["initial_speaker"] == "Daniel"
    assert dialogue.evidence["verified_speaker"] == "Mara"
    assert calls == [
        "analyze_story_dialogue_full_context",
        "verify_story_dialogue_full_context",
    ]


def test_verification_failure_never_silently_marks_dialogue_confident() -> None:
    revision = extract_source(
        project_id="book:verify-failure",
        content=b'"Hello," said Nita.\n',
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context["task"])
        if context["task"] in {
            "verify_story_dialogue_full_context",
            "retry_verify_story_dialogue_full_context",
        }:
            raise TimeoutError("verification timed out")
        return {
            "characters": [{"name": "Nita", "aliases": []}],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": "Nita",
                "role": "dialogue",
                "delivery": "",
                "confidence": 0.99,
            }],
        }

    result = annotate_span_batches(
        project_id="book:verify-failure",
        spans=revision.chapters[0].spans,
        speakers=[],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert dialogue.review_reason == "AI_VERIFICATION_UNAVAILABLE"
    assert dialogue.evidence["verification_status"] == "failed"
    assert dialogue.speaker_id == proposed_speaker_id(
        "book:verify-failure", "Nita",
    )
    assert calls == [
        "analyze_story_dialogue_full_context",
        "verify_story_dialogue_full_context",
        "retry_verify_story_dialogue_full_context",
    ]


def test_full_story_analysis_does_not_call_model_for_narration_only() -> None:
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


def test_proposed_speaker_id_from_ai_is_kept_as_canonical_candidate() -> None:
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
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert dialogue.speaker_id == provisional.id
    assert dialogue.speaker_candidate == "Nita"
    assert dialogue.review_reason is None


def test_low_confidence_proposed_speaker_stays_in_review() -> None:
    project_id = "book:provisional-confidence"
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
                "speaker": "Nita",
                "role": "dialogue",
                "delivery": "",
                "confidence": 0.82,
            }],
        }

    result = annotate_span_batches(
        project_id=project_id,
        spans=revision.chapters[0].spans,
        speakers=[provisional],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert dialogue.speaker_id == provisional.id
    assert dialogue.review_reason == "LOW_CONFIDENCE_SPEAKER"


def test_ambiguous_unknown_identity_stays_in_review_even_when_confident() -> None:
    project_id = "book:unknown-speaker"
    revision = extract_source(
        project_id=project_id,
        content=b'"Fire!" someone screamed.\n',
        source_format="txt",
    )

    def classifier(context):
        return {
            "characters": [{
                "name": "Unknown Crowd Member",
                "aliases": ["someone"],
            }],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": "Unknown Crowd Member",
                "role": "dialogue",
                "delivery": "alarmed",
                "confidence": 0.99,
            }],
        }

    result = annotate_span_batches(
        project_id=project_id,
        spans=revision.chapters[0].spans,
        speakers=[],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert dialogue.speaker_id == proposed_speaker_id(
        project_id, "Unknown Crowd Member",
    )
    assert dialogue.review_reason == "AMBIGUOUS_SPEAKER_IDENTITY"


def test_full_story_ai_is_semantic_authority_over_regex_attribution(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: False)
    revision = extract_source(
        project_id="book:tag-authority",
        content=b'"Run!" Daniel shouted.\n',
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context["task"])
        return {
            "characters": [],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": "Jo",
                "role": "dialogue",
                "delivery": "urgent",
                "confidence": 0.99,
            }],
        }

    result = annotate_span_batches(
        project_id="book:tag-authority",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("daniel-id", "Daniel"), Speaker("jo-id", "Jo")],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert dialogue.speaker_id == "jo-id"
    assert dialogue.review_reason is None
    assert dialogue.evidence["attribution_override"] is False
    assert dialogue.evidence["semantic_authority"] == "llm_full_story"
    assert dialogue.evidence["verification_status"] == "skipped"
    assert dialogue.evidence["verification_reasons"] == []
    assert "attribution_conflict" in dialogue.evidence["verification_soft_signals"]
    assert calls == ["analyze_story_dialogue_full_context"]


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
    )
    semantic_calls = [call for call in calls if "span_ids" in call]
    legacy_calls = [call for call in calls if "span_id" in call]
    assert len(semantic_calls) == 1
    assert len(legacy_calls) == 2
    assert len(result.annotations) == len(revision.chapters[0].spans)
    assert all(
        item.review_reason == "UNSUPPORTED_SPEAKER"
        for item in result.annotations
        if item.role == "dialogue"
    )


def test_small_chapter_uses_one_full_story_pass_plus_one_verifier() -> None:
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
            "characters": [{"name": "Nita", "aliases": []}],
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
        batch_size=1,
    )
    assert [call["task"] for call in calls] == [
        "analyze_story_dialogue_full_context",
        "verify_story_dialogue_full_context",
    ]
    assert len(calls[0]["span_ids"]) == 5
def test_easy_known_speaker_skips_second_llm_pass(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: False)
    revision = extract_source(
        project_id="book:adaptive-easy",
        content=b'"Hello."\\n',
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context)
        return {
            "characters": [],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": "Nita",
                "confidence": 0.99,
                "ambiguity": None,
            }],
        }

    result = annotate_span_batches(
        project_id="book:adaptive-easy",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("nita-id", "Nita")],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert [call["task"] for call in calls] == [
        "analyze_story_dialogue_full_context",
    ]
    assert dialogue.speaker_id == "nita-id"
    assert dialogue.evidence["verification_status"] == "skipped"
    assert dialogue.evidence["verification_required"] is False


def test_full_story_salvages_role_delivery_swap_without_rerun(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: False)
    revision = extract_source(
        project_id="book:schema-salvage",
        content=b'"Stop," Nita said.\\n',
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context["task"])
        return {
            "characters": [],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": "Nita",
                "role": "authoritative",
                "delivery": "dialogue",
                "confidence": 0.99,
            }],
        }

    result = annotate_span_batches(
        project_id="book:schema-salvage",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("nita-id", "Nita")],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert calls == ["analyze_story_dialogue_full_context"]
    assert dialogue.speaker_id == "nita-id"
    assert dialogue.delivery == "authoritative"
    assert dialogue.evidence["classification_schema_repair"] == "swapped_role_delivery"
    assert dialogue.evidence["verification_status"] == "skipped"


def test_full_story_retries_only_missing_span_after_bad_id(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: False)
    revision = extract_source(
        project_id="book:partial-repair",
        content=b'"One," Nita said.\\n"Two," Nita added.\\n',
        source_format="txt",
    )
    dialogue_spans = [
        span for span in revision.chapters[0].spans
        if span.structural_kind == "dialogue"
    ]
    calls = []

    def classifier(context):
        calls.append(context)
        if context["task"] == "analyze_story_dialogue_full_context":
            return {
                "characters": [],
                "spans": [
                    {
                        "span_id": dialogue_spans[0].id,
                        "speaker": "Nita",
                        "confidence": 0.99,
                        "ambiguity": None,
                    },
                    {
                        "span_id": "malformed-span-id",
                        "speaker": "Nita",
                        "confidence": 0.99,
                        "ambiguity": None,
                    },
                ],
            }
        assert context["task"] == "repair_story_dialogue_missing_spans"
        assert context["span_ids"] == [dialogue_spans[1].id]
        assert len(context["accepted_assignments"]) == 1
        return {
            "characters": [],
            "spans": [{
                "span_id": dialogue_spans[1].id,
                "speaker": "Nita",
                "confidence": 0.99,
                "ambiguity": None,
            }],
        }

    result = annotate_span_batches(
        project_id="book:partial-repair",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("nita-id", "Nita")],
        classifier=classifier,
    )
    assert [call["task"] for call in calls] == [
        "analyze_story_dialogue_full_context",
        "repair_story_dialogue_missing_spans",
    ]
    dialogue = [item for item in result.annotations if item.role == "dialogue"]
    assert len(dialogue) == 2
    assert all(item.speaker_id == "nita-id" for item in dialogue)
    repaired = next(item for item in dialogue if item.span_id == dialogue_spans[1].id)
    assert repaired.evidence["classification_partial_retry"] is True


def test_low_confidence_verifies_only_flagged_span(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: False)
    revision = extract_source(
        project_id="book:selective-verify",
        content=b'"One."\\n"Two."\\n',
        source_format="txt",
    )
    dialogue_spans = [
        span for span in revision.chapters[0].spans
        if span.structural_kind == "dialogue"
    ]
    calls = []

    def classifier(context):
        calls.append(context)
        if context["task"] == "analyze_story_dialogue_full_context":
            return {
                "characters": [],
                "spans": [
                    {
                        "span_id": dialogue_spans[0].id,
                        "speaker": "Nita",
                        "confidence": 0.99,
                        "ambiguity": None,
                    },
                    {
                        "span_id": dialogue_spans[1].id,
                        "speaker": "Nita",
                        "confidence": 0.80,
                        "ambiguity": "turn-taking is unclear",
                    },
                ],
            }
        assert context["task"] == "verify_story_dialogue_full_context"
        assert context["span_ids"] == [dialogue_spans[1].id]
        return {
            "characters": [],
            "spans": [{
                "span_id": dialogue_spans[1].id,
                "speaker": "Nita",
                "confidence": 0.99,
                "ambiguity": None,
            }],
        }

    result = annotate_span_batches(
        project_id="book:selective-verify",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("nita-id", "Nita")],
        classifier=classifier,
    )
    assert len(calls) == 2
    by_id = {item.span_id: item for item in result.annotations if item.role == "dialogue"}
    assert by_id[dialogue_spans[0].id].evidence["verification_status"] == "skipped"
    assert by_id[dialogue_spans[1].id].evidence["verification_status"] == "completed"
    assert "low_confidence" in by_id[dialogue_spans[1].id].evidence["verification_reasons"]
    assert "model_ambiguity" in by_id[dialogue_spans[1].id].evidence["verification_reasons"]


def test_audit_disagreement_escalates_to_full_context(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: True)
    revision = extract_source(
        project_id="book:audit-escalation",
        content=b'"Hello."\\n',
        source_format="txt",
    )
    span = next(
        item for item in revision.chapters[0].spans
        if item.structural_kind == "dialogue"
    )
    calls = []

    def classifier(context):
        calls.append(context["task"])
        speaker = "Nita" if context["task"] == "analyze_story_dialogue_full_context" else "Mara"
        return {
            "characters": [],
            "spans": [{
                "span_id": span.id,
                "speaker": speaker,
                "confidence": 0.99,
                "ambiguity": None,
            }],
        }

    result = annotate_span_batches(
        project_id="book:audit-escalation",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("nita-id", "Nita"), Speaker("mara-id", "Mara")],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert calls == [
        "analyze_story_dialogue_full_context",
        "verify_story_dialogue_full_context",
        "verify_story_dialogue_full_context_escalated",
    ]
    assert dialogue.speaker_id == "mara-id"
    assert dialogue.evidence["verification_scope"] == "full_context_escalated"
    assert dialogue.evidence["verification_changed"] is True


def test_full_story_accepts_missing_ambiguity_and_harmless_extra_fields(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: False)
    revision = extract_source(
        project_id="book:tolerant-shape",
        content=b'"Hello."\\n',
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context["task"])
        return {
            "characters": [],
            "diagnostic": "ignored",
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": "Nita",
                "confidence": 0.99,
                "note": "harmless extra metadata",
            }],
        }

    result = annotate_span_batches(
        project_id="book:tolerant-shape",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("nita-id", "Nita")],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert calls == ["analyze_story_dialogue_full_context"]
    assert dialogue.speaker_id == "nita-id"
    assert dialogue.evidence["classifier_ambiguity"] is None


def test_high_confidence_attribution_conflict_is_soft_signal(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: False)
    monkeypatch.setattr(
        "app.audiobook.annotation._direct_attribution_evidence",
        lambda *_args, **_kwargs: (["mara-id"], ["Mara"]),
    )
    revision = extract_source(
        project_id="book:soft-conflict",
        content=b'"Hello."\\n',
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context["task"])
        return {
            "characters": [],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": "Nita",
                "confidence": 0.99,
                "ambiguity": None,
            }],
        }

    result = annotate_span_batches(
        project_id="book:soft-conflict",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("nita-id", "Nita"), Speaker("mara-id", "Mara")],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert calls == ["analyze_story_dialogue_full_context"]
    assert dialogue.speaker_id == "nita-id"
    assert dialogue.evidence["verification_status"] == "skipped"
    assert dialogue.evidence["verification_reasons"] == []
    assert dialogue.evidence["verification_policy_version"] == "audiobook-verification-policy-v5"


def test_soft_signal_is_telemetry_without_hard_model_risk(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: False)
    monkeypatch.setattr(
        "app.audiobook.annotation._direct_attribution_evidence",
        lambda *_args, **_kwargs: (["mara-id"], ["Mara"]),
    )
    revision = extract_source(
        project_id="book:soft-conflict-low-confidence",
        content=b'"Hello."\\n',
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context)
        return {
            "characters": [],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": "Nita",
                "confidence": 0.97,
                "ambiguity": None,
            }],
        }

    result = annotate_span_batches(
        project_id="book:soft-conflict-low-confidence",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("nita-id", "Nita"), Speaker("mara-id", "Mara")],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert [call["task"] for call in calls] == [
        "analyze_story_dialogue_full_context",
    ]
    assert dialogue.evidence["verification_reasons"] == []
    assert "attribution_conflict" in dialogue.evidence["verification_soft_signals"]
    assert dialogue.evidence["verification_status"] == "skipped"


def test_verifier_receives_only_nearby_assignment_context(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: False)
    revision = extract_source(
        project_id="book:bounded-verification-context",
        content=(
            '"One."\\n"Two."\\n"Three."\\n"Four."\\n'
            '"Five."\\n"Six."\\n"Seven."\\n"Eight."\\n'
        ).encode(),
        source_format="txt",
    )
    dialogue_spans = [
        span for span in revision.chapters[0].spans
        if span.structural_kind == "dialogue"
    ]
    target = dialogue_spans[4]
    calls = []

    def classifier(context):
        calls.append(context)
        if context["task"] == "analyze_story_dialogue_full_context":
            return {
                "characters": [],
                "spans": [{
                    "span_id": span.id,
                    "speaker": "Nita",
                    "confidence": 0.80 if span.id == target.id else 0.99,
                    "ambiguity": None,
                } for span in dialogue_spans],
            }
        assert context["task"] == "verify_story_dialogue_full_context"
        assert context["span_ids"] == [target.id]
        assert len(context["chapter_assignments"]) <= 5
        assert all(
            set(item) == {"span_id", "speaker"}
            for item in context["chapter_assignments"]
        )
        return {
            "characters": [],
            "spans": [{
                "span_id": target.id,
                "speaker": "Nita",
                "confidence": 0.99,
                "ambiguity": None,
            }],
        }

    result = annotate_span_batches(
        project_id="book:bounded-verification-context",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("nita-id", "Nita")],
        classifier=classifier,
    )
    assert len(calls) == 2
    dialogue = next(
        item for item in result.annotations
        if item.span_id == target.id
    )
    assert dialogue.evidence["verification_status"] == "completed"


def test_stable_unknown_speaker_id_still_requires_verification(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: False)
    project_id = "book:unknown-stable-id"
    revision = extract_source(
        project_id=project_id,
        content=b'"Fire!"\\n',
        source_format="txt",
    )
    unknown = Speaker(
        proposed_speaker_id(project_id, "Unknown Crowd Member"),
        "Unknown Crowd Member",
        status="proposed",
    )
    calls = []

    def classifier(context):
        calls.append(context["task"])
        return {
            "characters": [],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": unknown.id,
                "confidence": 0.99,
                "ambiguity": None,
            }],
        }

    result = annotate_span_batches(
        project_id=project_id,
        spans=revision.chapters[0].spans,
        speakers=[unknown],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert calls == [
        "analyze_story_dialogue_full_context",
    ]
    assert dialogue.evidence["verification_reasons"] == []
    assert "ambiguous_identity" in dialogue.evidence["verification_soft_signals"]
    assert dialogue.evidence["verification_status"] == "skipped"
    assert dialogue.review_reason == "AMBIGUOUS_SPEAKER_IDENTITY"


def test_resolved_pronoun_note_does_not_trigger_verification(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: False)
    revision = extract_source(
        project_id="book:resolved-pronoun-note",
        content=b'Seraphine smiled.\\n"Still works," she said.\\n',
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context["task"])
        return {
            "characters": [],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": "Seraphine",
                "confidence": 0.99,
                "ambiguity": "pronoun-resolved to Seraphine",
            }],
        }

    result = annotate_span_batches(
        project_id="book:resolved-pronoun-note",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("seraphine-id", "Seraphine")],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert calls == ["analyze_story_dialogue_full_context"]
    assert dialogue.speaker_id == "seraphine-id"
    assert dialogue.evidence["verification_status"] == "skipped"
    assert dialogue.evidence["verification_policy_version"] == "audiobook-verification-policy-v5"


def test_true_competing_speaker_ambiguity_still_verifies(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: False)
    revision = extract_source(
        project_id="book:true-ambiguity",
        content=b'"What next?"\\n',
        source_format="txt",
    )
    calls = []

    def classifier(context):
        calls.append(context["task"])
        return {
            "characters": [],
            "spans": [{
                "span_id": context["span_ids"][0],
                "speaker": "Mara",
                "confidence": 0.99,
                "ambiguity": "Mara or Seraphine",
            }],
        }

    result = annotate_span_batches(
        project_id="book:true-ambiguity",
        spans=revision.chapters[0].spans,
        speakers=[
            Speaker("mara-id", "Mara"),
            Speaker("seraphine-id", "Seraphine"),
        ],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert calls == [
        "analyze_story_dialogue_full_context",
        "verify_story_dialogue_full_context",
    ]
    assert "model_ambiguity" in dialogue.evidence["verification_reasons"]


def test_single_edit_span_id_typo_is_repaired_without_retry(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _span_id: False)
    revision = extract_source(
        project_id="book:span-id-one-edit",
        content=b'"Hello."\\n',
        source_format="txt",
    )
    dialogue_span = next(
        span for span in revision.chapters[0].spans
        if span.structural_kind == "dialogue"
    )
    typo_id = dialogue_span.id[:-1]
    calls = []

    def classifier(context):
        calls.append(context["task"])
        return {
            "characters": [],
            "spans": [{
                "span_id": typo_id,
                "speaker": "Nita",
                "confidence": 0.99,
                "ambiguity": None,
            }],
        }

    result = annotate_span_batches(
        project_id="book:span-id-one-edit",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("nita-id", "Nita")],
        classifier=classifier,
    )
    dialogue = next(item for item in result.annotations if item.role == "dialogue")
    assert calls == ["analyze_story_dialogue_full_context"]
    assert dialogue.span_id == dialogue_span.id
    assert dialogue.speaker_id == "nita-id"
    assert dialogue.evidence["classification_span_id_repair"] == typo_id
    assert dialogue.evidence["classification_partial_retry"] is False


def test_audit_sampling_targets_at_most_one_span_per_window(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _key: True)
    revision = extract_source(
        project_id="book:window-audit",
        content=(
            '"One."\\n"Two."\\n"Three."\\n"Four."\\n'
            '"Five."\\n"Six."\\n"Seven."\\n"Eight."\\n'
        ).encode(),
        source_format="txt",
    )
    dialogue_spans = [
        span for span in revision.chapters[0].spans
        if span.structural_kind == "dialogue"
    ]
    calls = []

    def classifier(context):
        calls.append(context)
        if context["task"] == "analyze_story_dialogue_full_context":
            return {
                "characters": [],
                "spans": [{
                    "span_id": span.id,
                    "speaker": "Nita",
                    "confidence": 0.99,
                    "ambiguity": None,
                } for span in dialogue_spans],
            }
        assert context["task"] == "verify_story_dialogue_full_context"
        assert len(context["span_ids"]) == 1
        target_id = context["span_ids"][0]
        return {
            "characters": [],
            "spans": [{
                "span_id": target_id,
                "speaker": "Nita",
                "confidence": 0.99,
                "ambiguity": None,
            }],
        }

    result = annotate_span_batches(
        project_id="book:window-audit",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("nita-id", "Nita")],
        classifier=classifier,
    )
    assert len(calls) == 2
    dialogue = [item for item in result.annotations if item.role == "dialogue"]
    audited = [
        item for item in dialogue
        if "audit_sample" in item.evidence["verification_reasons"]
    ]
    assert len(audited) == 1
    assert audited[0].evidence["verification_audit_scope"] == "window"


def test_context_only_dialogue_is_visible_but_not_a_classifier_target(monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.annotation._audit_selected", lambda _key: False)
    revision = extract_source(
        project_id="book:context-only-dialogue",
        source_format="txt",
        content=b'"Context quote."\n"Target quote."\n',
    )
    dialogue = [
        span for span in revision.chapters[0].spans
        if span.structural_kind == "dialogue"
    ]
    assert len(dialogue) == 2
    calls = []

    def classifier(context):
        calls.append(context)
        return {
            "characters": [],
            "spans": [{
                "span_id": dialogue[1].id,
                "speaker": "Nita",
                "confidence": 0.99,
                "ambiguity": None,
            }],
        }

    result = annotate_span_batches(
        project_id="book:context-only-dialogue",
        spans=revision.chapters[0].spans,
        speakers=[Speaker("nita-id", "Nita")],
        classifier=classifier,
        dialogue_target_ids={dialogue[1].id},
    )
    assert len(calls) == 1
    assert calls[0]["span_ids"] == [dialogue[1].id]
    assert f'<DIALOGUE id="{dialogue[0].id}" target="false"/>' in calls[0]["story_text"]
    assert f'<DIALOGUE id="{dialogue[1].id}" target="true"/>' in calls[0]["story_text"]

    by_id = {
        item.span_id: item for item in result.annotations
        if item.role == "dialogue"
    }
    assert by_id[dialogue[0].id].speaker_id == narrator_id(
        "book:context-only-dialogue"
    )
    assert (
        by_id[dialogue[0].id].evidence["semantic_authority"]
        == "analysis_policy_context"
    )
    assert by_id[dialogue[1].id].speaker_id == "nita-id"
