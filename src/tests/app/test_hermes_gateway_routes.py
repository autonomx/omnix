from __future__ import annotations

from app.gateway.main import create_gateway_app


def test_hermes_gateway_routes_are_registered() -> None:
    app = create_gateway_app()
    paths = {route.path for route in app.routes}

    assert "/api/hermes/status" in paths
    assert "/api/hermes/test" in paths
    assert "/api/hermes/recent" in paths


def test_hermes_gateway_routes_are_hidden_from_openapi() -> None:
    schema_paths = create_gateway_app().openapi()["paths"]

    assert "/api/hermes/status" not in schema_paths
    assert "/api/hermes/test" not in schema_paths
    assert "/api/hermes/recent" not in schema_paths
