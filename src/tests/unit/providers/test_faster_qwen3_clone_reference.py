from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np

from app.providers import faster_qwen3_tts_provider as tts


def test_mp3_clone_uses_its_sample_and_transcript(tmp_path, monkeypatch) -> None:
    sample = tmp_path / "ehsan.mp3"
    sample.write_bytes(b"sample")
    (tmp_path / "Ehsan.json").write_text(json.dumps({"ref_text": "Spoken reference words."}), encoding="utf-8")
    default_ref = tmp_path / "default_ref.wav"
    default_ref.write_bytes(b"other voice")
    monkeypatch.setattr(tts, "VOICE_CLONES_DIR", tmp_path)
    monkeypatch.setattr(
        "app.assets.canonical_voice_clones.discover_canonical_voice_clone_assets",
        lambda: [SimpleNamespace(id="voice-cloning:ehsan", storage_path=str(sample))],
    )

    for speaker in ("voice-cloning:ehsan", "Ehsan"):
        path, saved_text = tts._clone_reference(speaker)
        assert path == str(sample)
        assert saved_text == "Spoken reference words."
        assert tts._clone_conditioning({}, {"xvec_only": True}, saved_text) == (saved_text, False)

    assert tts._clone_conditioning({"xvec_only": True}, {}, saved_text) == (saved_text, True)
    assert tts._clone_conditioning({}, {"xvec_only": True}, "") == ("", True)


def test_missing_clone_id_does_not_use_another_voice(tmp_path, monkeypatch) -> None:
    (tmp_path / "default_ref.wav").write_bytes(b"other voice")
    monkeypatch.setattr(tts, "VOICE_CLONES_DIR", tmp_path)
    monkeypatch.setattr(
        "app.assets.canonical_voice_clones.discover_canonical_voice_clone_assets",
        lambda: [],
    )

    assert tts._clone_reference("voice-cloning:missing") == (None, "")


def test_batch_and_stream_forward_full_reference_conditioning(tmp_path, monkeypatch) -> None:
    sample = tmp_path / "ehsan.mp3"
    sample.write_bytes(b"sample")
    (tmp_path / "ehsan.json").write_text(json.dumps({"ref_text": "Spoken words."}), encoding="utf-8")
    monkeypatch.setattr(
        "app.assets.canonical_voice_clones.discover_canonical_voice_clone_assets",
        lambda: [SimpleNamespace(id="voice-cloning:ehsan", storage_path=str(sample))],
    )
    calls = []

    class Model:
        def generate_voice_clone(self, **kwargs):
            calls.append(kwargs)
            return [np.full(100, 0.1, dtype=np.float32)], 24000

        def generate_voice_clone_streaming(self, **kwargs):
            calls.append(kwargs)
            yield np.full(100, 0.1, dtype=np.float32), 24000, {}

    provider = tts.FasterQwen3TTSProvider(config={"device": "cpu", "xvec_only": True})
    monkeypatch.setattr(provider, "_get_model", lambda: Model())
    monkeypatch.setattr(provider, "_numpy_to_wav_bytes", lambda audio, rate: b"wav")

    assert provider._generate_audio_impl("Hello", speaker="voice-cloning:ehsan")["success"]
    assert list(provider.generate_audio_stream("Hello", speaker="voice-cloning:ehsan"))
    assert len(calls) == 2
    for call in calls:
        assert call["ref_audio"] == str(sample)
        assert call["ref_text"] == "Spoken words."
        assert call["xvec_only"] is False


def test_resolved_audiobook_defaults_preserve_transcript_conditioning() -> None:
    provider = tts.FasterQwen3TTSProvider(config={"device": "cpu", "xvec_only": True})
    resolved = provider.resolve_generation_parameters({})
    assert tts._clone_conditioning(resolved, provider._model_config, "Spoken words.") == (
        "Spoken words.", False,
    )
    assert tts._clone_conditioning(resolved, provider._model_config, "") == ("", True)
    explicit = provider.resolve_generation_parameters({"xvec_only": True})
    assert tts._clone_conditioning(explicit, provider._model_config, "Spoken words.") == (
        "Spoken words.", True,
    )
