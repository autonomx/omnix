import json

from app.rpg.api import rpg_presentation_routes as routes


class DummyRequest:
    def __init__(self, payload=None):
        self._payload = payload or {}
        self.method = "POST"

    async def json(self):
        return self._payload


def _decode_response(response):
    if hasattr(response, "body"):
        return json.loads(response.body)
    return response


def test_switch_visual_provider_route_disabled(monkeypatch):
    store = {"rpg_visual": {"enabled": True, "visual_provider": "flux_klein"}}

    monkeypatch.setattr(routes, "load_settings", lambda: dict(store))
    monkeypatch.setattr(routes, "save_settings", lambda value: store.update(value))

    response = routes.switch_visual_provider_route(
        DummyRequest({"provider": "disabled", "enabled": False, "force_reload": True})
    )
    if hasattr(response, "__await__"):
        import asyncio
        response = asyncio.run(response)

    data = _decode_response(response)
    assert data["ok"] is True
    assert data["enabled"] is False
    assert data["selected_provider"] == "disabled"


def test_unload_visual_provider_route_returns_disabled(monkeypatch):
    store = {"rpg_visual": {"enabled": True, "visual_provider": "flux_klein"}}

    monkeypatch.setattr(routes, "load_settings", lambda: dict(store))
    monkeypatch.setattr(routes, "save_settings", lambda value: store.update(value))

    response = routes.unload_visual_provider_route(DummyRequest())
    if hasattr(response, "__await__"):
        import asyncio
        response = asyncio.run(response)

    data = _decode_response(response)
    assert data["ok"] is True
    assert data["enabled"] is False
    assert data["provider"] == "disabled"