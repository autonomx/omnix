"""Guard the current RPG compatibility route inventory.

Supported compatibility endpoints have response-contract coverage under
``tests/api/gateway``. These checks keep that active surface registered and
document classic paths that were deliberately retired during the FastAPI
gateway migration.
"""

from __future__ import annotations

import pytest

from app.gateway.main import create_gateway_app


ACTIVE_COMPAT_ROUTES = (
    ("GET", "/api/rpg/adventure/templates"),
    ("POST", "/api/rpg/adventure/validate"),
    ("POST", "/api/rpg/adventure/preview"),
    ("POST", "/api/rpg/adventure/inspect-world"),
    ("POST", "/api/rpg/adventure/inspect-world-snapshot"),
    ("POST", "/api/rpg/adventure/compare-world"),
    ("POST", "/api/rpg/adventure/compare-entity"),
    ("POST", "/api/rpg/adventure/simulate-step"),
    ("POST", "/api/rpg/adventure/simulation-state"),
    ("POST", "/api/rpg/inspect/timeline"),
    ("POST", "/api/rpg/inspect/timeline_tick"),
    ("POST", "/api/rpg/inspect/tick_diff"),
    ("POST", "/api/rpg/inspect/npc_reasoning"),
    ("POST", "/api/rpg/player/state"),
    ("POST", "/api/rpg/player/journal"),
    ("POST", "/api/rpg/player/codex"),
    ("POST", "/api/rpg/player/objectives"),
    ("POST", "/api/rpg/player/encounter"),
)

RETIRED_COMPAT_ROUTES = (
    ("POST", "/api/rpg/adventure/start"),
    ("POST", "/api/rpg/adventure/regenerate"),
    ("POST", "/api/rpg/adventure/regenerate-item"),
    ("POST", "/api/rpg/adventure/regenerate-multiple"),
    ("POST", "/api/rpg/dialogue/start"),
    ("POST", "/api/rpg/dialogue/message"),
    ("POST", "/api/rpg/dialogue/end"),
    ("POST", "/api/rpg/encounter/start"),
    ("POST", "/api/rpg/encounter/action"),
    ("POST", "/api/rpg/encounter/npc_turn"),
    ("POST", "/api/rpg/encounter/end"),
    ("POST", "/api/rpg/player/dialogue/enter"),
    ("POST", "/api/rpg/player/dialogue/exit"),
    ("POST", "/api/rpg/player/inventory"),
    ("POST", "/api/rpg/player/inventory/use"),
    ("POST", "/api/rpg/player/inventory/registry"),
    ("POST", "/api/rpg/player/party"),
    ("POST", "/api/rpg/player/party/recruit"),
    ("POST", "/api/rpg/player/party/remove"),
    ("POST", "/api/rpg/gm/force_npc_goal"),
    ("POST", "/api/rpg/gm/force_faction_trend"),
    ("POST", "/api/rpg/gm/debug_note"),
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
    ("POST", "/api/rpg/presentation/scene"),
    ("POST", "/api/rpg/presentation/dialogue"),
    ("POST", "/api/rpg/presentation/speakers"),
    ("POST", "/setup-flow"),
    ("POST", "/session-bootstrap"),
    ("POST", "/intro-scene"),
    ("POST", "/save-load-ux"),
    ("POST", "/narrative-recap"),
    ("POST", "/api/rpg/character_ui"),
    ("POST", "/api/rpg/character_inspector"),
    ("POST", "/api/rpg/character_inspector/detail"),
    ("POST", "/api/rpg/world_inspector"),
    ("POST", "/api/rpg/character_portrait/request"),
    ("POST", "/api/rpg/character_portrait/result"),
    ("POST", "/api/rpg/package/export"),
    ("POST", "/api/rpg/package/import"),
    ("POST", "/api/rpg/package/validate"),
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


@pytest.mark.parametrize(("method", "path"), ACTIVE_COMPAT_ROUTES)
def test_active_rpg_compatibility_routes_are_registered(
    gateway_route_registry: frozenset[tuple[str, str]], method: str, path: str
) -> None:
    assert (path, method) in gateway_route_registry


@pytest.mark.parametrize(("method", "path"), RETIRED_COMPAT_ROUTES)
def test_retired_classic_rpg_routes_stay_unregistered(
    gateway_route_registry: frozenset[tuple[str, str]], method: str, path: str
) -> None:
    assert (path, method) not in gateway_route_registry
