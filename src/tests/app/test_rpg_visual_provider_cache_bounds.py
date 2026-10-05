from types import SimpleNamespace

from app.apps.rpg.visual import providers


def test_rpg_visual_provider_cache_expires_and_invalidates(monkeypatch) -> None:
    providers.unload_image_provider_cache()
    now = {"value": 10.0}
    unloaded: list[bool] = []
    instance = SimpleNamespace(unload=lambda: unloaded.append(True))
    monkeypatch.setattr(providers.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(providers, "IMAGE_PROVIDER_CACHE_TTL_SECONDS", 5.0)
    monkeypatch.setattr(providers, "load_settings", lambda: {"rpg_visual": {}})
    monkeypatch.setattr(
        providers,
        "build_visual_provider",
        lambda _settings: ("test-provider", instance),
    )

    assert providers.get_image_provider() is instance
    assert providers.get_loaded_image_provider() is instance
    now["value"] = 16.0

    assert providers.get_loaded_image_provider() is None
    assert unloaded == [True]
    assert providers.get_image_provider_cache_key() == ""
