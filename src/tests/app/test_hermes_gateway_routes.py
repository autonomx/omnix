from __future__ import annotations

from tests.support.routers import effective_routes

from app.gateway.main import create_gateway_app


HERMES_HIDDEN_ROUTES = {
    "/api/hermes/status",
    "/api/hermes/test",
    "/api/hermes/recent",
    "/api/hermes/adapter/preview",
    "/api/hermes/candidate/demo",
    "/api/hermes/rpg/context",
    "/api/hermes/rpg/suggestions",
    "/api/hermes/rpg/turn-readout",
    "/api/hermes/plan",
    "/api/hermes/approve",
}


def test_hermes_gateway_routes_are_registered() -> None:
    app = create_gateway_app()
    paths = {route.path for route in effective_routes(app)}

    assert HERMES_HIDDEN_ROUTES.issubset(paths)

