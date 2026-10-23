"""Campaigns to play through, and a client that plays them through the production routes (RQ-0.2, RQ-0.3).

Each launcher starts a campaign the way the app does: Aurelia and Vesper-9 are imported from their bundles,
adopted and launched from an opening; the starter town is a classic new game. ``Playthrough`` plays turns
through ``POST /api/rpg/sessions/{id}/turn`` and the other state-changing routes, and reads state back
from the play screen's session route and from the stored campaign.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

POSTGRES = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]
WORLDS = ("aurelia", "vesper", "starter")


def in_worlds(*worlds: str, **xfail: str) -> list[Any]:
    """Parameters for a scenario played in ``worlds`` (default: all three); a world named in ``xfail`` is a
    strict expected failure with that reason, which names the package that fixes it."""
    return [
        pytest.param(world, marks=pytest.mark.xfail(strict=True, reason=xfail[world])) if world in xfail else world
        for world in (worlds or WORLDS)
    ]


BUNDLES = Path(__file__).resolve().parents[4] / "resources/examples/rpg/world-bundles"
AURELIA = BUNDLES / "aurelia-echoes-beyond-the-gate"
VESPER = BUNDLES / "vesper-9-city-of-borrowed-minds"


@lru_cache(maxsize=None)
def bundle_bytes(source_dir: Path) -> bytes:
    spec = importlib.util.spec_from_file_location(f"materialize_{source_dir.name.replace('-', '_')}", source_dir / "materialize.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    builder = getattr(module, "_build_bundle", None) or module.build_bundle
    return builder(source_dir)


def _import_and_adopt(source_dir: Path, tmp_path, monkeypatch, *, name: str) -> str:
    from app.apps.rpg.genesis.worlds.world_adoption import adopt_shared_world
    from app.apps.rpg.genesis.worlds.world_bundle_import import import_world_bundle
    from app.persistence.repository_registry import register_feature_repositories

    register_feature_repositories("rpg")  # as composition does (the world library's repositories)
    monkeypatch.setenv("OMNIX_RESOURCES_DIR", str(tmp_path))
    world_id = f"world:{name}-{uuid.uuid4().hex[:10]}"
    imported = import_world_bundle(bundle_bytes(source_dir), target_world_id=world_id)
    adopt_shared_world(world_id, bundle_sha256=imported["bundle_sha256"])
    return world_id


def _launch_scenario(world_id: str, scenario_match: str, player: dict[str, Any]) -> str:
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant
    from app.apps.rpg.edge.api.feature_routes.rpg_world_library_routes import SESSION_CAMPAIGN_SESSIONS
    from app.apps.rpg.genesis.worlds.published_launch import launch_published_scenario

    with unit_of_work() as work:
        context = current_tenant()
        scenarios = sorted(work.world_library.iter_scenarios(context, world_id=world_id), key=lambda row: str(row["id"]))
        scenario = next(row for row in scenarios if scenario_match in str(row["id"]))
        document = dict(work.world_library.list_scenario_revisions(context, str(scenario["id"]))[0]["document"])
        work.rollback()
    launched = launch_published_scenario(
        sessions=SESSION_CAMPAIGN_SESSIONS,
        world_id=world_id,
        world_revision=int(document["world_revision"]),
        world_release=int(document["compatible_release"]),
        scenario_id=str(document["scenario_id"]),
        scenario_revision=int(document["revision"]),
        player=player,
        features={"llm_narration": True, "image_generation": False},
    )
    return str(launched["session_id"])


def launch_aurelia(tmp_path, monkeypatch, *, opening: str = "gateborn") -> tuple[str, str]:
    """Aurelia from its bundle, launched from an opening ("Gateborn: First Light" by default): (session, world)."""
    world_id = _import_and_adopt(AURELIA, tmp_path, monkeypatch, name="aurelia-play")
    return _launch_scenario(world_id, opening, {"name": "Wren", "pronouns": "they/them"}), world_id


def launch_vesper(tmp_path, monkeypatch, *, opening: str = "") -> tuple[str, str]:
    """Vesper-9 from its bundle. It carries lore only, so its authored openings are prepared for launch first
    (deterministically, without World Forge), then the first prepared one launches: (session, world)."""
    from app.apps.rpg.genesis.worlds.launch_repair_service import prepare_opening_scenarios_for_launch

    world_id = _import_and_adopt(VESPER, tmp_path, monkeypatch, name="vesper-play")
    prepared = prepare_opening_scenarios_for_launch(world_id)
    scenario_ids = [str(row["scenario_id"]) for row in prepared.get("prepared") or ()]
    assert scenario_ids, prepared
    match = next((scenario_id for scenario_id in scenario_ids if opening and opening in scenario_id), scenario_ids[0])
    return _launch_scenario(world_id, match, {"name": "Wren", "pronouns": "they/them"}), world_id


def new_starter_game(seed: int = 7) -> str:
    """A classic new game in the starter town."""
    from app.apps.rpg.session.new_game import RpgNewGameRequest, create_new_game_session

    return str(create_new_game_session(RpgNewGameRequest(seed=seed))["session_id"])


def new_genesis_game() -> str:
    """A new game made through the creation wizard's genesis contract (the World Forge path, forge disabled)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.apps.rpg.edge.api.feature_routes.rpg_session_routes import register_rpg_session_routes
    from tests.rpg.session.test_rpg_new_game_genesis_route import _wizard_payload
    from tests.support.routers import include_router_registrar

    app = FastAPI()
    include_router_registrar(app, register_rpg_session_routes)
    response = TestClient(app, base_url="http://127.0.0.1").post("/api/rpg/new-game", json=_wizard_payload())
    assert response.status_code == 200, response.text[:300]
    return str(response.json()["session_id"])


def copper(purse: dict[str, Any] | None) -> int:
    purse = purse or {}
    return int(purse.get("gold") or 0) * 100 + int(purse.get("silver") or 0) * 10 + int(purse.get("copper") or 0)


class Playthrough:
    """Plays one campaign through the production routes."""

    def __init__(self, session_id: str) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.apps.rpg.edge.api.feature_routes.rpg_session_routes import register_rpg_session_routes
        from app.apps.rpg.edge.api.feature_routes.rpg_tactical_spatial_routes import register_rpg_tactical_spatial_routes
        from tests.support.routers import include_router_registrar

        app = FastAPI()
        include_router_registrar(app, register_rpg_session_routes)
        include_router_registrar(app, register_rpg_tactical_spatial_routes)
        self.session_id = session_id
        self.client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})

    # -- acting ----------------------------------------------------------------------------------------
    def post_turn(self, command: str, *, submission_id: str = ""):
        """A turn through the turn route; the client names its submission in a header, as the play screen does."""
        headers = {"x-omnix-rpg-submission-id": submission_id} if submission_id else {}
        return self.client.post(f"/api/rpg/sessions/{self.session_id}/turn", json={"command": command}, headers=headers)

    def turn(self, command: str, *, submission_id: str = "") -> dict[str, Any]:
        response = self.post_turn(command, submission_id=submission_id)
        assert response.status_code == 200, f"{command!r}: {response.status_code} {response.text[:500]}"
        return response.json()

    def loadout(self, action: str, item: str):
        return self.client.post(f"/api/rpg/sessions/{self.session_id}/loadout-action",
                                json={"action": action, "item_name": item})

    def tactical_move(self, destination: tuple[int, int], *, actor_id: str | None = None, submission_id: str = "move-1"):
        """Move the hero on the campaign's current map, at the revisions the play screen last saw."""
        instance = self.map_instance()
        return self.client.post(
            f"/api/rpg/map-instances/{instance['map_instance_id']}/tactical/move",
            json={
                "submission_id": submission_id,
                "command_id": f"command:{submission_id}",
                "actor_id": actor_id or f"player:{self.session_id}",
                "destination": list(destination),
                "expected_map_state_revision": int(instance["snapshot"]["map_state_revision"]),
                "expected_campaign_revision": self.revision(),
            },
        )

    def tactical_attack(self, target_id: str, *, actor_id: str | None = None, submission_id: str = "attack-1"):
        instance = self.map_instance()
        return self.client.post(
            f"/api/rpg/map-instances/{instance['map_instance_id']}/tactical/attack",
            json={
                "submission_id": submission_id,
                "command_id": f"command:{submission_id}",
                "actor_id": actor_id or f"player:{self.session_id}",
                "target_id": target_id,
                "expected_map_state_revision": int(instance["snapshot"]["map_state_revision"]),
                "expected_campaign_revision": self.revision(),
            },
        )

    # -- reading -------------------------------------------------------------------------------------
    def public(self) -> dict[str, Any]:
        """The session as the play screen reads it."""
        response = self.client.get(f"/api/rpg/sessions/{self.session_id}")
        assert response.status_code == 200, response.text[:300]
        return response.json()["session"]["state"]

    def stored(self) -> dict[str, Any]:
        """The stored campaign document."""
        from app.apps.rpg.session.persistence.session_records import load_session_from_postgres

        session = load_session_from_postgres(self.session_id)
        assert session is not None
        return session

    def revision(self) -> int:
        from app.apps.rpg.session.persistence.session_records import load_session_version_from_postgres

        version = load_session_version_from_postgres(self.session_id)
        assert version is not None
        return int(version[0])

    def map_instance(self) -> dict[str, Any]:
        from app.persistence.unit_of_work import unit_of_work
        from app.runtime.tenant_context import current_tenant

        map_instance_id = str(self.stored().get("state", {}).get("current_map_instance_id") or "")
        with unit_of_work() as work:
            instance = work.map_instances.get_instance(current_tenant(), map_instance_id)
            work.rollback()
        assert instance is not None, map_instance_id
        return {**instance, "map_instance_id": map_instance_id}

    def simulation(self) -> dict[str, Any]:
        return dict(self.stored().get("simulation_state") or {})

    def player_state(self) -> dict[str, Any]:
        return dict(self.simulation().get("player_state") or {})  # the simulation keeps one from the first turn

    def purse(self) -> int:
        """The purse in copper, as the play screen shows it."""
        return copper(self.public()["player"]["currency"])

    def purses(self) -> dict[str, int]:
        """Every stored copy of the purse, in copper: they must agree (the simulation's exist from the first turn)."""
        state = self.player_state()
        copies = {"sheet": self.purse(), "simulation": state.get("currency"),
                  "simulation_inventory": (state.get("inventory_state") or {}).get("currency")}
        return {name: value if isinstance(value, int) else copper(value)
                for name, value in copies.items() if value is not None}

    def inventory(self) -> dict[str, int]:
        """What the play screen lists in the pack, by name and quantity."""
        items: dict[str, int] = {}
        for item in self.public()["player"]["inventory"]:
            items[str(item["name"])] = items.get(str(item["name"]), 0) + int(item.get("quantity") or 0)
        return items

    def hp(self) -> int:
        return int(self.public()["player"]["resources"]["hp"]["current"])

    def location(self) -> str:
        return str(self.player_state().get("location_id") or "")

    def present(self) -> list[str]:
        return list(self.stored()["runtime_state"].get("current_scene", {}).get("present_npc_ids") or ())

    def quests(self) -> dict[str, dict[str, Any]]:
        return {str(quest["title"]): quest for quest in self.public()["quests"]}

    def party(self) -> list[str]:
        companions = (self.player_state().get("party_state") or {}).get("companions") or ()
        return [str(companion.get("npc_id")) for companion in companions]

    def survival(self) -> dict[str, Any]:
        return dict(self.simulation().get("survival") or {})

    def combat(self) -> dict[str, Any]:
        return dict(self.simulation().get("combat_state") or {})

    def turn_count(self) -> int:
        return int(self.public()["turn_count"])

    def turn_rows(self) -> list[dict[str, Any]]:
        """The campaign's committed turn rows, oldest first (with each turn's state patch)."""
        from app.persistence.unit_of_work import unit_of_work
        from app.runtime.tenant_context import current_tenant
        from app.apps.rpg.foundation.persistence.rpg_repository import _TURN_COLUMNS, _turn

        context = current_tenant()
        with unit_of_work() as work:
            rows = work.connection.execute(
                f"SELECT {_TURN_COLUMNS} FROM omnix_rpg_turns WHERE workspace_id = %s AND campaign_id = %s ORDER BY sequence",
                (context.workspace_id, self.session_id),
            ).fetchall()
            work.rollback()
        return [_turn(row) for row in rows]

    def facts(self) -> dict[str, Any]:
        """The concrete state a player can check: place, people, purse, pack, health, quests, party, needs, fight."""
        public = self.public()
        player = self.player_state()
        combat = self.combat()
        skills = {name: {key: skill.get(key) for key in ("level", "xp") if key in skill}
                  for name, skill in sorted((player.get("skills") or {}).items()) if isinstance(skill, dict)}
        return {
            "location_id": self.location(),
            "location_name": public.get("current_location_name"),
            "present_npc_ids": sorted(self.present()),
            "purse_copper": self.purse(),
            "inventory": dict(sorted(self.inventory().items())),
            "equipment": sorted(str(row.get("name")) for row in public["player"].get("equipment") or ()),
            "hp": self.hp(),
            "quests": {title: quest.get("status") for title, quest in sorted(self.quests().items())},
            "party": self.party(),
            "survival": {key: self.survival().get(key) for key in ("hunger", "thirst", "fatigue")},
            "skills": skills,
            "combat": {
                "active": bool(combat.get("active")),
                "participants": {actor: (participant.get("resources") or {}).get("hp", participant.get("hp"))
                                 for actor, participant in sorted((combat.get("participants") or {}).items())},
            },
            "turn_count": self.turn_count(),
        }


def fact_changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """What a turn changed, fact by fact: numbers as deltas, collections as what was added and removed."""
    changes: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old == new or key == "turn_count":
            continue
        if isinstance(old, int) and isinstance(new, int) and not isinstance(old, bool):
            changes[key] = new - old
        elif isinstance(old, dict) and isinstance(new, dict) and key in {"inventory", "survival"}:
            changes[key] = {name: (new.get(name) or 0) - (old.get(name) or 0)
                            for name in sorted(set(old) | set(new)) if old.get(name) != new.get(name)}
        elif isinstance(old, dict) and isinstance(new, dict):
            changes[key] = {name: new.get(name) for name in sorted(set(old) | set(new)) if old.get(name) != new.get(name)}
        elif isinstance(old, list) and isinstance(new, list):
            changes[key] = {"added": [item for item in new if item not in old],
                            "removed": [item for item in old if item not in new]}
        else:
            changes[key] = new
    return changes
