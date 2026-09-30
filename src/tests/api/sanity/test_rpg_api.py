"""Route-registration checks for the current gateway RPG surface.

The old Flask ``/api/rpg/games`` lifecycle is retired by
``app.rpg.api.rpg_session_routes``. Current response behavior is covered by
``tests/api/gateway/test_gateway_rpg_*_compat.py`` and the session route tests.
"""

from __future__ import annotations

import pytest

from app.gateway.main import create_gateway_app


CURRENT_RPG_COMPAT_ROUTES = (
    ("POST", "/api/rpg/session/list"),
    ("POST", "/api/rpg/session/get"),
    ("GET", "/api/rpg/sessions"),
    ("GET", "/api/rpg/sessions/{session_id}"),
)


@pytest.fixture(scope="module")
def gateway_route_registry() -> frozenset[tuple[str, str]]:
    gateway = create_gateway_app()
    return frozenset(
        (route.path, method)
        for route in gateway.routes
        if hasattr(route, "path")
        for method in getattr(route, "methods", ())
    )


def test_gateway_health_routes_are_registered(gateway_route_registry) -> None:
    assert ("/health", "GET") in gateway_route_registry
    assert ("/api/health", "GET") in gateway_route_registry


@pytest.mark.parametrize(("method", "path"), CURRENT_RPG_COMPAT_ROUTES)
def test_current_rpg_session_routes_are_registered(
    gateway_route_registry: frozenset[tuple[str, str]], method: str, path: str
) -> None:
    assert (path, method) in gateway_route_registry


def test_classic_rpg_games_namespace_stays_retired(gateway_route_registry) -> None:
    assert not any(
        path == "/api/rpg/games" or path.startswith("/api/rpg/games/")
        for path, _method in gateway_route_registry
    )


def test_legacy_adventure_start_route_stays_retired(gateway_route_registry) -> None:
    assert ("/api/rpg/adventure/start", "POST") not in gateway_route_registry
