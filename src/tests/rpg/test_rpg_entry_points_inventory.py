"""RQ-0.8: every mutating RPG route and RPG job kind is in docs/architecture/RPG_ENTRY_POINTS.md.

A new POST, PUT, PATCH or DELETE route under the RPG feature, its compatibility router or the Hermes routers fails
this test until the inventory lists it with a turn kind (roadmap §4.1) or an exemption; a listed route that no
longer exists fails it too.
"""
from __future__ import annotations

from pathlib import Path
import re
from types import SimpleNamespace

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "docs/architecture/RPG_ENTRY_POINTS.md"
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
TURN_KINDS = ("player_text", "structured_action", "world_tick", "system")


def _flatten(routes) -> list:
    """Routes of a router, descending into included routers (FastAPI wraps them lazily)."""
    flat = []
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            flat.extend(_flatten(original.routes))
        else:
            flat.append(route)
    return flat


def registered_mutating_routes() -> set[str]:
    from app.apps.rpg.edge.api.compat_router import create_rpg_compatibility_router
    from app.apps.rpg.edge.api.feature_routes import create_rpg_routes_router
    from app.apps.rpg.edge.hermes.feature import FEATURE as HERMES
    from app.apps.rpg.feature import FEATURE as RPG

    routers: list[APIRouter] = [
        create_rpg_routes_router(SimpleNamespace(runtime_state=SimpleNamespace())),
        create_rpg_compatibility_router(),
    ]
    routers += [factory(SimpleNamespace(runtime_state=SimpleNamespace())) for factory in HERMES.routers]
    assert len(RPG.routers) == 2, "a new RPG router factory must be added to this test"
    found = set()
    for router in routers:
        for route in _flatten(router.routes):
            for method in sorted(set(getattr(route, "methods", None) or ()) & MUTATING):
                found.add(f"{method} {route.path}")
    return found


def inventory_rows() -> dict[str, str]:
    rows = {}
    for line in INVENTORY.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\| `((?:POST|PUT|PATCH|DELETE) /[^`]+)` \|", line)
        if match:
            assert match.group(1) not in rows, f"listed twice: {match.group(1)}"
            rows[match.group(1)] = line.rsplit("|", 2)[-2].strip()
    return rows


def test_every_mutating_rpg_route_is_inventoried():
    registered = registered_mutating_routes()
    listed = inventory_rows()
    assert len(registered) > 100
    assert sorted(registered - set(listed)) == [], "add these routes to RPG_ENTRY_POINTS.md"
    assert sorted(set(listed) - registered) == [], "these listed routes no longer exist"


def test_every_inventoried_route_has_a_turn_kind_or_an_exemption():
    for route, decision in inventory_rows().items():
        assert decision.startswith("Exemption, ") or any(f"`{kind}`" in decision for kind in TURN_KINDS) or decision.startswith(
            "Split:"
        ), f"{route}: {decision}"


def test_every_rpg_job_kind_is_inventoried():
    from app.apps.rpg.feature import FEATURE

    text = INVENTORY.read_text(encoding="utf-8")
    kinds = {spec.type for spec in FEATURE.job_handlers}
    from app.apps.rpg.genesis.forge.async_coordinator import CAMPAIGN_EXPANSION_JOB_TYPE, CAMPAIGN_GENESIS_JOB_TYPE
    from app.apps.rpg.genesis.worlds.generation_jobs import WORLD_TOPIC_JOB_TYPE
    from app.apps.rpg.genesis.worlds.profile_generation_jobs import WORLD_PROFILE_JOB_TYPE
    from app.apps.rpg.genesis.worlds.progressive_materialization_job_planning import MATERIALIZATION_JOB_TYPE

    kinds |= {CAMPAIGN_GENESIS_JOB_TYPE, CAMPAIGN_EXPANSION_JOB_TYPE, WORLD_TOPIC_JOB_TYPE, WORLD_PROFILE_JOB_TYPE,
              MATERIALIZATION_JOB_TYPE}
    missing = sorted(kind for kind in kinds if f"| `{kind}` |" not in text)
    assert missing == []
