from app.rpg.visual.providers import (
    build_visual_provider,
    get_image_provider,
    get_loaded_image_provider_name,
    has_visual_provider,
    image_generation_enabled,
    list_visual_provider_options,
    resolve_visual_provider_key,
    unload_image_provider_cache,
)


def test_visual_provider_registry_lists_flux_and_disabled():
    options = list_visual_provider_options()
    keys = {item["key"] for item in options}
    assert "disabled" in keys
    assert "flux_klein" in keys


def test_resolve_visual_provider_defaults_to_flux_klein():
    assert resolve_visual_provider_key({}) == "flux_klein"


def test_resolve_visual_provider_honors_disabled_flag():
    assert resolve_visual_provider_key({"enabled": False}) == "disabled"


def test_resolve_visual_provider_honors_explicit_provider_key():
    assert resolve_visual_provider_key({"visual_provider": "flux_klein"}) == "flux_klein"


def test_resolve_visual_provider_normalizes_disabled_aliases():
    assert resolve_visual_provider_key({"visual_provider": "off"}) == "disabled"
    assert resolve_visual_provider_key({"provider": "disabled"}) == "disabled"


def test_build_visual_provider_returns_disabled_provider():
    key, provider = build_visual_provider({"enabled": False})
    assert key == "disabled"
    assert provider.provider_name == "disabled"


def test_build_visual_provider_returns_flux_provider():
    key, provider = build_visual_provider({"visual_provider": "flux_klein"})
    assert key == "flux_klein"
    assert provider.provider_name == "flux_klein"


def test_has_visual_provider_reports_known_keys():
    assert has_visual_provider("disabled") is True
    assert has_visual_provider("flux_klein") is True
    assert has_visual_provider("missing_provider") is False


def test_backcompat_cache_accessors(monkeypatch):
    monkeypatch.setattr(
        "app.rpg.visual.providers.load_settings",
        lambda: {"rpg_visual": {"enabled": False}},
    )
    unload_image_provider_cache()
    provider = get_image_provider()
    assert provider.provider_name == "disabled"
    assert image_generation_enabled() is False
    assert get_loaded_image_provider_name() == "disabled"