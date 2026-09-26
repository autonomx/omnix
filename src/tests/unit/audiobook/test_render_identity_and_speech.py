from __future__ import annotations

from dataclasses import replace

import pytest

from app.audiobook.render_keys import RenderIdentity, invalidation_for
from app.audiobook.speech_plan import build_speech_plan, split_speech_plan


def _identity(plan_hash: str) -> RenderIdentity:
    return RenderIdentity(
        source_span_hash="a" * 64, annotation_revision="ann:1", speaker_id="speaker:1",
        casting_revision="casting:1", voice_revision="b" * 64,
        reference_audio_hash=None, provider_id="qwen", model_id="qwen3-tts",
        model_revision="model:1", language="en", delivery_instruction="calm",
        speech_plan_hash=plan_hash, generation_parameters={"speed": 1.0}, seed=42,
    )


def test_speech_plan_is_auditable_and_does_not_change_source() -> None:
    source = "Dr. Smith paid $4.95 on 2026-09-18."
    plan = build_speech_plan(source)
    assert plan.source_text == source
    assert "Doctor Smith paid four dollars and ninety-five cents" in plan.tts_input_text
    assert any(item.rule == "date" for item in plan.transformations)
    assert build_speech_plan(source) == plan


@pytest.mark.parametrize("prefix", ["Ehsan: ", "Ehsan:", "  Kinming:\t", "Mary Jane: "])
def test_dialogue_speaker_label_is_removed_only_from_audio(prefix: str) -> None:
    source = prefix + "It’s working again.\n"
    plan = build_speech_plan(source, structural_kind="dialogue")
    assert plan.source_text == source
    assert plan.tts_input_text == "It’s working again.\n"
    assert plan.transformations[0].rule == "speaker_label"
    assert plan.transformations[0].source == prefix
    assert plan.transformations[0].spoken == ""
    assert _identity(plan.hash).key() != _identity(build_speech_plan(source).hash).key()


def test_label_removal_keeps_pronunciation_inside_quote_and_source_offsets() -> None:
    source = "Ehsan: Ehsan earned $286."
    plan = build_speech_plan(source, structural_kind="dialogue", overrides={"Ehsan": "Eh-sahn"})
    assert plan.tts_input_text == "Eh-sahn earned two hundred eighty-six dollars."
    assert [change.rule for change in plan.transformations] == ["speaker_label", "override", "currency"]
    assert all(source[change.source_start:change.source_end] == change.source for change in plan.transformations)


@pytest.mark.parametrize("source", [
    "Ehsan: a character in this story.", "Chapter One: Opening",
    '"Ehsan: It’s working again."', "The time is 6:42.",
])
def test_narration_and_labels_inside_quoted_dialogue_are_preserved(source: str) -> None:
    narration = build_speech_plan(source)
    assert not any(change.rule == "speaker_label" for change in narration.transformations)
    if source.startswith('"'):
        assert build_speech_plan(source, structural_kind="dialogue").tts_input_text == narration.tts_input_text


def test_long_labelled_dialogue_splits_without_reintroducing_label() -> None:
    source = "Ehsan: " + "The story continues. " * 80
    plan = build_speech_plan(source, structural_kind="dialogue")
    segments = split_speech_plan(plan, max_chars=75)
    assert "".join(segment.source_text for _, _, segment in segments) == source
    assert "".join(segment.tts_input_text for _, _, segment in segments) == plan.tts_input_text
    assert sum(change.rule == "speaker_label" for _, _, segment in segments for change in segment.transformations) == 1


def test_selected_occurrence_is_excluded_without_global_word_removal() -> None:
    source = "Testing\nKinming was testing the strategy. Testing continued."
    plan = build_speech_plan(source, exclusions=((0, 7),))
    assert plan.source_text == source
    assert plan.tts_input_text == "\nKinming was testing the strategy. Testing continued."
    assert plan.transformations[0].rule == "speech_exclusion"
    assert plan.hash != build_speech_plan(source).hash


def test_exclusions_override_pronunciation_and_merge_with_speaker_label() -> None:
    source = "Ehsan: Ehsan paid $286."
    plan = build_speech_plan(source, structural_kind="dialogue", overrides={"Ehsan": "Eh-sahn"}, exclusions=((0, 12), (8, 13)))
    assert plan.tts_input_text == "paid two hundred eighty-six dollars."
    assert plan.transformations[0].source == "Ehsan: Ehsan "


def test_excluding_whole_span_yields_empty_speech() -> None:
    assert build_speech_plan("Testing", exclusions=((0, 7),)).tts_input_text == ""


@pytest.mark.parametrize("exclusions", [((-1, 2),), ((0, 100),), ((2, 2),)])
def test_exclusions_must_be_bound_to_source_offsets(exclusions) -> None:
    with pytest.raises(ValueError, match="outside source"):
        build_speech_plan("Testing", exclusions=exclusions)


def test_unrelated_pronunciation_does_not_invalidate_span() -> None:
    source = "Nita said hello."
    original = build_speech_plan(source, overrides={"Nita": "Nee-ta"})
    unrelated = build_speech_plan(source, overrides={"Nita": "Nee-ta", "Xylophone": "Zy-lo-phone"})
    changed = build_speech_plan(source, overrides={"Nita": "Ny-ta"})
    assert original.hash == unrelated.hash
    assert original.hash != changed.hash
    assert _identity(original.hash).key() == _identity(unrelated.hash).key()
    assert _identity(original.hash).key() != _identity(changed.hash).key()


def test_pronunciation_applies_to_each_whole_word_regardless_of_case() -> None:
    plan = build_speech_plan(
        "Ehsan spoke. Then ehsan answered. Ehsani listened.",
        overrides={"Ehsan": "Eh-sahn"},
    )
    assert plan.tts_input_text == "Eh-sahn spoke. Then Eh-sahn answered. Ehsani listened."
    assert [change.source for change in plan.transformations] == ["Ehsan", "ehsan"]


def test_pronunciation_preserves_case_for_all_caps_acronyms() -> None:
    plan = build_speech_plan(
        "US agents spoke to us.",
        overrides={"US": "U-S"},
    )
    assert plan.tts_input_text == "U-S agents spoke to us."
    assert [change.source for change in plan.transformations] == ["US"]


def test_render_key_excludes_export_metadata_and_includes_material_settings() -> None:
    request = _identity("c" * 64)
    assert request.key() == _identity("c" * 64).key()
    assert request.key() != replace(request, voice_revision="d" * 64).key()
    assert request.key() != replace(request, seed=43).key()
    assert request.key() != replace(request, generation_parameters={"speed": 1.1}).key()


def test_invalidation_matrix_keeps_export_only_changes_out_of_tts() -> None:
    assert invalidation_for("cover").render == "none"
    assert invalidation_for("export_settings").master == "none"
    assert invalidation_for("casting").render == "affected_speaker_spans"
    assert invalidation_for("canonical_source").render == "all"



def test_resolved_provider_defaults_change_render_identity() -> None:
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    base = _identity("e" * 64)
    first = FasterQwen3TTSProvider(config={"device": "cpu", "temperature": 0.7})
    second = FasterQwen3TTSProvider(config={"device": "cpu", "temperature": 0.9})
    first_identity = replace(
        base, generation_parameters=first.resolve_generation_parameters({}),
    )
    second_identity = replace(
        base, generation_parameters=second.resolve_generation_parameters({}),
    )
    assert first_identity.key() != second_identity.key()


def test_long_narration_splits_without_losing_source_or_spoken_text() -> None:
    # Roughly the text volume of a few hundred short pages, in one source span.
    source = ("The lantern shone across Hollow Bay. " * 9000)
    plan = build_speech_plan(source)
    segments = split_speech_plan(plan)
    assert len(segments) > 1
    assert all(len(item.tts_input_text) <= 450 for _, _, item in segments)
    assert "".join(item.source_text for _, _, item in segments) == source
    assert "".join(item.tts_input_text for _, _, item in segments) == plan.tts_input_text
    assert segments == split_speech_plan(plan)


def test_segment_cut_never_breaks_a_pronunciation_replacement() -> None:
    source = ("A story continues. " * 12) + "Hollow Bay" + (" shines brightly. " * 12)
    plan = build_speech_plan(source, overrides={"Hollow Bay": "the luminous harbor"})
    segments = split_speech_plan(plan, max_chars=75)
    assert "".join(item.tts_input_text for _, _, item in segments) == plan.tts_input_text
    assert sum(len(item.transformations) for _, _, item in segments) == len(plan.transformations)
    assert all(len(item.tts_input_text) <= 75 for _, _, item in segments)
