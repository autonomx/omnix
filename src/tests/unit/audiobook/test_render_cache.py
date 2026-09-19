from __future__ import annotations

from app.audiobook.render_cache import valid_render_blob
from app.persistence.blob_store import LocalBlobStore
from app.providers.audio_base import AudioProviderCapability, BaseTTSProvider


def test_missing_or_corrupt_blob_is_never_a_cache_hit(tmp_path) -> None:
    blobs = LocalBlobStore(tmp_path)
    content = b"RIFF....WAVE"
    stored = blobs.put_bytes("audiobook/render/one.wav", content)
    render = {"audio_asset_id": "ab:audio:one", "audio_checksum": stored["checksum_sha256"]}
    asset = {"id": "ab:audio:one", "module": "audiobook", "lifecycle_status": "active",
             "checksum_sha256": stored["checksum_sha256"], "storage_provider": blobs.provider,
             "storage_key": "audiobook/render/one.wav"}
    assert valid_render_blob(render, asset, blobs)
    blobs.put_bytes("audiobook/render/one.wav", b"damaged")
    assert not valid_render_blob(render, asset, blobs)
    blobs.delete("audiobook/render/one.wav")
    assert not valid_render_blob(render, asset, blobs)


class _TestProvider(BaseTTSProvider):
    @property
    def provider_name(self) -> str:
        return "test"

    def get_speakers(self):
        return []

    def generate_audio(self, text, speaker=None, language=None, **kwargs):
        return {"success": True, "text": text, "speaker": speaker, "language": language, "options": kwargs}

    def voice_clone(self, voice_id, audio_data, ref_text=None):
        return {"success": True}


def test_batch_contract_preserves_order_without_claiming_gpu_batching() -> None:
    provider = _TestProvider(config={})
    output = provider.generate_audio_batch([
        {"text": "first", "speaker": "narrator"},
        {"text": "second", "language": "en", "parameters": {"seed": 1}},
    ])
    assert [item["text"] for item in output] == ["first", "second"]
    assert output[1]["options"] == {"seed": 1}
    assert AudioProviderCapability.OFFLINE_BATCH not in provider.get_capabilities()
