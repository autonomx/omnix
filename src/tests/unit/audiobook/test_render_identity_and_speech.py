from __future__ import annotations

from dataclasses import replace

from app.audiobook.render_keys import RenderIdentity, invalidation_for
from app.audiobook.speech_plan import build_speech_plan


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


def test_unrelated_pronunciation_does_not_invalidate_span() -> None:
    source = "Nita said hello."
    original = build_speech_plan(source, overrides={"Nita": "Nee-ta"})
    unrelated = build_speech_plan(source, overrides={"Nita": "Nee-ta", "Xylophone": "Zy-lo-phone"})
    changed = build_speech_plan(source, overrides={"Nita": "Ny-ta"})
    assert original.hash == unrelated.hash
    assert original.hash != changed.hash
    assert _identity(original.hash).key() == _identity(unrelated.hash).key()
    assert _identity(original.hash).key() != _identity(changed.hash).key()


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
