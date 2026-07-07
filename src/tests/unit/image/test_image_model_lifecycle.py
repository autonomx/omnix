from __future__ import annotations

from app.image import lifecycle


class _FakeProvider:
    def __init__(self) -> None:
        self.loaded = False
        self.warmed_up = False
        self.unload_calls = 0
        self.warmup_calls = 0

    def load(self) -> None:
        self.loaded = True

    def warmup(self, *, force: bool = False) -> dict:
        self.warmup_calls += 1
        self.warmed_up = True
        return {
            "ok": True,
            "warmed_up": True,
            "skipped": False,
            "state": "completed",
            "force": force,
        }

    def unload(self) -> None:
        self.loaded = False
        self.warmed_up = False
        self.unload_calls += 1

    def is_loaded(self) -> bool:
        return self.loaded

    def runtime_status(self) -> dict:
        return {"warmed_up": self.warmed_up}


def test_image_provider_residency_tracks_real_loaded_state(monkeypatch):
    provider = _FakeProvider()
    lifecycle.unload_all_image_providers()
    monkeypatch.setattr(lifecycle, "_build_provider", lambda _name: provider)

    assert lifecycle.is_image_provider_loaded("flux_klein") is False
    assert lifecycle.get_image_provider_cache_status()["loaded_providers"] == []

    loaded = lifecycle.load_image_provider("flux_klein")
    assert loaded["ok"] is True
    assert loaded["provider"] == "flux_klein"
    assert loaded["loaded"] is True
    assert loaded["runtime"]["warmed_up"] is False
    assert lifecycle.is_image_provider_loaded("flux_klein") is True
    assert lifecycle.get_image_provider_cache_status()["loaded_providers"] == ["flux_klein"]

    warmed = lifecycle.warm_image_provider("flux_klein")
    assert warmed["ok"] is True
    assert warmed["provider"] == "flux_klein"
    assert warmed["warmed_up"] is True
    assert provider.warmup_calls == 1
    assert lifecycle.get_image_provider_cache_status()["runtime"]["flux_klein"]["warmed_up"] is True

    unloaded = lifecycle.unload_image_provider("flux_klein")
    assert unloaded["ok"] is True
    assert unloaded["loaded"] is False
    assert unloaded["unloaded"] is True
    assert provider.unload_calls == 1
    assert lifecycle.is_image_provider_loaded("flux_klein") is False
