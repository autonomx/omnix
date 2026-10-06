import pytest

from app.providers import catalog, tts_artifacts


def test_only_catalogued_tts_providers_with_local_artifacts_are_resolved(monkeypatch):
    local = {spec.id for spec in catalog.specs("tts")
             if tts_artifacts.LOCAL_ARTIFACTS in spec.capabilities}
    assert local == {"faster-qwen3-tts"}
    for provider_id in ("parakeet", "lmstudio", "unknown"):
        with pytest.raises(tts_artifacts.LocalArtifactsUnavailable, match="unavailable"):
            tts_artifacts.local_model_artifacts(provider_id)


def test_the_port_asks_the_catalogued_provider(monkeypatch, tmp_path):
    class FakeProvider:
        @staticmethod
        def local_model_artifacts():
            return tts_artifacts.LocalModelArtifacts(model_id="Fake-TTS", directory=tmp_path)

    spec = catalog.ProviderSpec("fake-tts", "tts", "fake", "FakeProvider",
                                frozenset({tts_artifacts.LOCAL_ARTIFACTS}))
    monkeypatch.setattr(catalog.ProviderSpec, "load", lambda self: FakeProvider)
    monkeypatch.setattr(tts_artifacts, "specs", lambda kind: (spec,) if kind == "tts" else ())

    assert tts_artifacts.local_model_artifacts("fake-tts") == tts_artifacts.LocalModelArtifacts(
        model_id="Fake-TTS", directory=tmp_path,
    )
