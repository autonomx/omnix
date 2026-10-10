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
