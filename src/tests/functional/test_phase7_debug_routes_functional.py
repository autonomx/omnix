"""Guard the active debug endpoints on the composed FastAPI gateway.

Behavioral coverage for structured logging and the supported event endpoint
lives in ``tests/rpg/test_rpg_debug_logging.py``. This route inventory prevents
the retired Flask-only state mutation endpoints from returning to production.
"""

from __future__ import annotations

from tests.support.routers import effective_routes

import pytest

from app.composition.gateway.main import create_gateway_app


ACTIVE_DEBUG_ROUTES = {
    ("GET", "/api/rpg/debug/log-status"),
    ("POST", "/api/rpg/debug/event"),
}

RETIRED_DEBUG_ROUTES = {
    ("POST", "/api/rpg/debug/state"),
    ("POST", "/api/rpg/debug/npc"),
    ("POST", "/api/rpg/debug/faction"),
    ("POST", "/api/rpg/debug/step"),
    ("POST", "/api/rpg/debug/inject_event"),
    ("POST", "/api/rpg/debug/seed_rumor"),
    ("POST", "/api/rpg/debug/force_alliance"),
    ("POST", "/api/rpg/debug/force_faction_position"),
    ("POST", "/api/rpg/debug/force_npc_belief"),
    ("POST", "/api/rpg/debug/snapshots"),
    ("POST", "/api/rpg/debug/snapshot"),
    ("POST", "/api/rpg/debug/rollback"),
}


@pytest.fixture(scope="module")
def gateway_route_registry() -> frozenset[tuple[str, str]]:
    gateway = create_gateway_app()
    return frozenset(
        (route.path, method)
        for route in effective_routes(gateway)
        if route.path
        for method in getattr(route, "methods", ())
    )


@pytest.mark.parametrize(("method", "path"), sorted(ACTIVE_DEBUG_ROUTES))
def test_supported_debug_endpoints_are_registered(
    gateway_route_registry: frozenset[tuple[str, str]], method: str, path: str
) -> None:
    assert (path, method) in gateway_route_registry


@pytest.mark.parametrize(("method", "path"), sorted(RETIRED_DEBUG_ROUTES))
def test_retired_debug_mutations_stay_unregistered(
    gateway_route_registry: frozenset[tuple[str, str]], method: str, path: str
) -> None:
    assert (path, method) not in gateway_route_registry
