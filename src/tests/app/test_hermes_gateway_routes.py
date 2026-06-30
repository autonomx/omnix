from __future__ import annotations

from app.gateway.main import create_gateway_app


HERMES_HIDDEN_ROUTES = {
    "/api/hermes/status",
    "/api/hermes/test",
    "/api/hermes/recent",
    "/api/hermes/candidate/demo",
    "/api/hermes/rpg/context",
    "/api/hermes/approve",
}


def test_hermes_gateway_routes_are_registered() -> None:
    app = create_gateway_app()
    paths = {route.path for route in app.routes}

    assert HERMES_HIDDEN_ROUTES.issubset(paths)


def test_hermes_gateway_routes_are_hidden_from_openapi() -> None:
    schema_paths = create_gateway_app().openapi()["paths"]

    for path in HERMES_HIDDEN_ROUTES:
        assert path not in schema_paths
