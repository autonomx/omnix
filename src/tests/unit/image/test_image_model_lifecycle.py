from __future__ import annotations

from app.image import lifecycle


class _FakeProvider:
    def __init__(self) -> None:
        self.loaded = False
        self.unload_calls = 0

    def load(self) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False
        self.unload_calls += 1

    def is_loaded(self) -> bool:
        return self.loaded


def test_image_provider_residency_tracks_real_loaded_state(monkeypatch):
    provider = _FakeProvider()
    lifecycle.unload_all_image_providers()
    monkeypatch.setattr(lifecycle, "_build_provider", lambda _name: provider)

    assert lifecycle.is_image_provider_loaded("flux_klein") is False
    assert lifecycle.get_image_provider_cache_status()["loaded_providers"] == []

    loaded = lifecycle.load_image_provider("flux_klein")
    assert loaded == {"ok": True, "provider": "flux_klein", "loaded": True}
    assert lifecycle.is_image_provider_loaded("flux_klein") is True
    assert lifecycle.get_image_provider_cache_status()["loaded_providers"] == ["flux_klein"]

    unloaded = lifecycle.unload_image_provider("flux_klein")
    assert unloaded["ok"] is True
    assert unloaded["loaded"] is False
    assert unloaded["unloaded"] is True
    assert provider.unload_calls == 1
    assert lifecycle.is_image_provider_loaded("flux_klein") is False


def test_image_provider_cache_expires_and_respects_capacity(monkeypatch):
    first = _FakeProvider()
    second = _FakeProvider()
    now = {"value": 10.0}
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(lifecycle, "IMAGE_PROVIDER_CACHE_TTL_SECONDS", 5.0)
    monkeypatch.setattr(lifecycle, "MAX_CACHED_IMAGE_PROVIDERS", 1)
    lifecycle.unload_all_image_providers()
    monkeypatch.setattr(
        lifecycle,
        "_build_provider",
        lambda name: first if name == "first" else second,
    )

    assert lifecycle.get_or_create_image_provider("first") is first
    assert lifecycle.get_or_create_image_provider("second") is second
    assert first.unload_calls == 1

    now["value"] = 16.0
    assert lifecycle.get_cached_provider("second") is None
    assert second.unload_calls == 1
