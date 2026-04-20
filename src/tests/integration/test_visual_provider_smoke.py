from __future__ import annotations

from app.rpg.visual.providers import (
    get_image_provider,
    unload_image_provider_cache,
    image_generation_enabled,
    get_loaded_image_provider_name,
)
from app.rpg.visual.runtime_status import (
    validate_visual_runtime,
)


def test_visual_provider_disabled_path(monkeypatch):
    """
    End-to-end check:
    - settings disabled
    - provider resolves to disabled
    - cache + accessors behave correctly
    """

    monkeypatch.setattr(
        "app.rpg.visual.providers.load_settings",
        lambda: {"rpg_visual": {"enabled": False}},
    )

    unload_image_provider_cache()

    provider = get_image_provider()

    assert provider.provider_name == "disabled"
    assert image_generation_enabled() is False
    assert get_loaded_image_provider_name() == "disabled"


def test_visual_runtime_status_disabled():
    payload = validate_visual_runtime("disabled")

    assert payload["provider"] == "disabled"
    assert payload["ready"] is True
    assert payload["status"] == "disabled"
    assert payload["error"] == ""


def test_visual_runtime_status_unknown_provider():
    payload = validate_visual_runtime("unknown_provider")

    assert payload["provider"] == "unknown_provider"
    assert payload["ready"] is False
    assert payload["error"] == "unknown_visual_provider"


def test_visual_provider_cache_reload(monkeypatch):
    """
    Ensure cache resets correctly between provider loads.
    """

    # first load disabled
    monkeypatch.setattr(
        "app.rpg.visual.providers.load_settings",
        lambda: {"rpg_visual": {"enabled": False}},
    )

    unload_image_provider_cache()
    provider_a = get_image_provider()
    assert provider_a.provider_name == "disabled"

    # now switch config to flux
    monkeypatch.setattr(
        "app.rpg.visual.providers.load_settings",
        lambda: {"rpg_visual": {"visual_provider": "flux_klein"}},
    )

    unload_image_provider_cache()
    provider_b = get_image_provider()

    assert provider_b.provider_name == "flux_klein"
    assert provider_b is not provider_a


def test_unload_route_contract(monkeypatch):
    """
    Validate that unloading provider results in disabled state.
    """

    from app.rpg.api.rpg_presentation_routes import unload_visual_provider_route

    class DummyRequest:
        pass

    # force enabled first
    monkeypatch.setattr(
        "app.shared.load_settings",
        lambda: {"rpg_visual": {"visual_provider": "flux_klein", "enabled": True}},
    )

    monkeypatch.setattr(
        "app.shared.save_settings",
        lambda s: None,
    )

    response = unload_visual_provider_route(DummyRequest())

    # FastAPI-style responses may return dict or JSONResponse
    if hasattr(response, "body"):
        import json
        data = json.loads(response.body)
    else:
        data = response

    assert data["ok"] is True
    assert data["enabled"] is False
    assert data["provider"] == "disabled"