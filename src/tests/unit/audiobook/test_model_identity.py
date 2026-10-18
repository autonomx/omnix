from __future__ import annotations

import os

import pytest

from app.apps.audiobook import model_identity
from app.providers import tts_artifacts


def test_model_revision_tracks_weights_and_tokenizer(tmp_path, monkeypatch) -> None:
    (tmp_path / "model.safetensors").write_bytes(b"model version one")
    tokenizer = tmp_path / "speech_tokenizer"
    tokenizer.mkdir()
    (tokenizer / "model.safetensors").write_bytes(b"codec version one")
    (tmp_path / "config.json").write_text('{"revision": 1}', encoding="utf-8")
    real_port = tts_artifacts.local_model_artifacts

    def port(provider_id):
        if provider_id == "faster-qwen3-tts":
            return tts_artifacts.LocalModelArtifacts(model_id="Qwen3-TTS", directory=tmp_path)
        return real_port(provider_id)

    monkeypatch.setattr(tts_artifacts, "local_model_artifacts", port)

    original = model_identity.current_model_identity()
    assert original["model_revision"].startswith("sha256:")
    assert original["artifact_count"] == 3
    model_identity.assert_model_revision("faster-qwen3-tts", "Qwen3-TTS",
                                         str(original["model_revision"]))

    codec = tokenizer / "model.safetensors"
    codec.write_bytes(b"codec version two")
    # A same-size rewrite can keep its mtime on a coarse filesystem clock (Linux updates mtimes per tick), and the
    # content hash is cached by size and mtime: date it a second later, as a replaced model file would be.
    stat = codec.stat()
    os.utime(codec, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    updated = model_identity.current_model_identity()
    assert updated["model_revision"] != original["model_revision"]
    with pytest.raises(model_identity.ModelIdentityError, match="does not match"):
        model_identity.assert_model_revision("faster-qwen3-tts", "Qwen3-TTS",
                                             str(original["model_revision"]))
    with pytest.raises(model_identity.ModelIdentityError, match="unavailable"):
        model_identity.assert_model_revision("another-provider", "other",
                                             str(updated["model_revision"]))
    with pytest.raises(model_identity.ModelIdentityError, match="does not match"):
        model_identity.assert_model_revision("faster-qwen3-tts", "other",
                                             str(updated["model_revision"]))


def test_the_default_identity_is_the_selected_engine(tmp_path, monkeypatch) -> None:
    (tmp_path / "model-00001-of-00002.safetensors").write_bytes(b"fish weights")
    (tmp_path / "codec.pth").write_bytes(b"fish codec")
    monkeypatch.setattr("app.providers.service.load_settings", lambda: {"audio_provider_tts": "fish-s2-pro"})
    monkeypatch.setattr(tts_artifacts, "local_model_artifacts", lambda provider_id: (
        tts_artifacts.LocalModelArtifacts(model_id="Fish-Audio-S2-Pro", directory=tmp_path)
        if provider_id == "fish-s2-pro" else pytest.fail(f"asked for {provider_id}")))

    identity = model_identity.current_model_identity()

    assert identity["provider_id"] == "fish-s2-pro"
    assert identity["model_id"] == "Fish-Audio-S2-Pro"
    # The codec weights are part of the revision.
    assert identity["artifact_count"] == 2
