from app.rpg.visual.providers import (
    get_loaded_image_provider_name,
    get_visual_provider_status_payload,
    preload_image_provider,
    switch_image_provider_runtime,
    unload_image_provider_cache,
)


def test_preload_disabled_provider(monkeypatch):
    monkeypatch.setattr(
        "app.rpg.visual.providers.load_settings",
        lambda: {"rpg_visual": {"enabled": False}},
    )
    unload_image_provider_cache()
    provider = preload_image_provider(force_reload=True)
    assert provider.provider_name == "disabled"
    assert get_loaded_image_provider_name() == "disabled"


def test_hot_switch_runtime_between_disabled_and_flux():
    unload_image_provider_cache()

    key_a, provider_a = switch_image_provider_runtime(
        provider_key="disabled",
        enabled=False,
        provider_config={"enabled": False},
        force_reload=True,
    )
    assert key_a == "disabled"
    assert provider_a.provider_name == "disabled"
    assert get_loaded_image_provider_name() == "disabled"

    key_b, provider_b = switch_image_provider_runtime(
        provider_key="flux_klein",
        enabled=True,
        provider_config={"visual_provider": "flux_klein", "enabled": True},
        force_reload=True,
    )
    assert key_b == "flux_klein"
    assert provider_b.provider_name == "flux_klein"
    assert get_loaded_image_provider_name() == "flux_klein"


def test_visual_provider_status_payload_contains_runtime_keys(monkeypatch):
    monkeypatch.setattr(
        "app.rpg.visual.providers.load_settings",
        lambda: {"rpg_visual": {"enabled": False}},
    )
    unload_image_provider_cache()
    preload_image_provider(force_reload=True)
    payload = get_visual_provider_status_payload()
    assert payload["loaded"] is True
    assert payload["loaded_provider"] == "disabled"
    assert "runtime_status" in payload
    assert "options" in payload