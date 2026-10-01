"""Smoke-check the current composed gateway surface.

Detailed request and response contracts live in ``tests/api/gateway``. The
former Flask sanity suite depended on a removed ``client`` fixture and tested
routes that no longer belong to the production gateway.
"""

from __future__ import annotations

from tests.support.routers import effective_routes

import pytest

from app.gateway.main import create_gateway_app


CURRENT_CORE_ROUTES = (
    ("GET", "/health"),
    ("GET", "/api/health"),
    ("GET", "/api/settings"),
    ("POST", "/api/settings"),
    ("GET", "/api/sessions"),
    ("POST", "/api/sessions"),
    ("GET", "/api/providers"),
    ("POST", "/api/providers/refresh"),
    ("GET", "/api/chat/sessions"),
    ("POST", "/api/chat/sessions"),
    ("GET", "/api/jobs"),
    ("POST", "/api/jobs"),
    ("GET", "/api/jobs/events"),
)


@pytest.fixture(scope="module")
def gateway_route_registry() -> frozenset[tuple[str, str]]:
    gateway = create_gateway_app()
    return frozenset(
        (route.path, method)
        for route in effective_routes(gateway)
        if hasattr(route, "path")
        for method in getattr(route, "methods", ())
    )


@pytest.mark.parametrize(("method", "path"), CURRENT_CORE_ROUTES)
def test_current_gateway_core_routes_are_registered(
    gateway_route_registry: frozenset[tuple[str, str]], method: str, path: str
) -> None:
    assert (path, method) in gateway_route_registry
