from __future__ import annotations

from typing import Any

from app.rpg.map_grid_contracts import (
    GridMapDefinition,
    GridSpawnPoint,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.worlds.contracts import MapDefinitionBinding
from app.rpg.worlds.published_launch import launch_published_scenario
from app.rpg.worlds.service import (
    compile_scenario_revision,
    compile_world_release,
    compile_world_revision,
)


def test_published_scenario_launch_creates_bound_campaign_without_world_forge(
    monkeypatch,
) -> None:
    definition = with_grid_definition_hashes(
        GridMapDefinition(
            map_id="map:rusty_flagon",
            level="interior",
            definition_revision=1,
            world_id="world:published",
            world_revision=1,
            width=4,
            height=4,
            terrain_palette=(
                TerrainRule(code=".", terrain_id="floor", walkable=True),
            ),
            terrain_rows=("....",) * 4,
            spawn_points=(
                GridSpawnPoint(
                    spawn_point_id="spawn:arrival",
                    cell=(1, 1),
                    tags=("arrival", "player"),
                ),
            ),
            metadata={"location_id": "rusty_flagon_tavern"},
        )
    )
    world_revision = compile_world_revision(
        world_id="world:published",
        revision=1,
        title="Published World",
        canon={"campaign_template": "classic_fantasy"},
        entity_manifest={},
        topology={"locations": ["rusty_flagon_tavern"], "routes": []},
        blueprint_requirements=(
            {
                "map_id": definition.map_id,
                "simulation_readiness": "navigable",
            },
        ),
    )
    release = compile_world_release(
        world_revision,
        release=1,
        map_bindings=(
            MapDefinitionBinding(
                map_id=definition.map_id,
                blueprint_revision=1,
                definition_revision=definition.definition_revision,
                definition_hash=definition.definition_hash,
                semantic_interface_hash=definition.semantic_interface_hash,
                simulation_readiness="navigable",
            ),
        ),
        certification={"launch_ready": True, "missing_requirements": []},
    )
    scenario = compile_scenario_revision(
        scenario_id="scenario:opening",
        revision=1,
        world_revision=world_revision,
        compatible_release=1,
        starting_location_id="rusty_flagon_tavern",
    )
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "app.rpg.worlds.published_launch.load_published_resources",
        lambda **_kwargs: (world_revision, release, scenario),
    )
    monkeypatch.setattr(
        "app.rpg.worlds.published_launch.load_release_definitions",
        lambda *_args, **_kwargs: {definition.map_id: definition},
    )
    monkeypatch.setattr(
        "app.rpg.worlds.published_launch.require_scenario_writable",
        lambda *_args, **_kwargs: {"status": "published"},
    )
    monkeypatch.setattr(
        "app.rpg.worlds.published_launch.bootstrap_local_tenant",
        lambda _database: object(),
    )
    monkeypatch.setattr(
        "app.rpg.worlds.published_launch.create_new_game_session",
        lambda _request: {
            "ok": True,
            "session_id": "campaign:published",
            "session": {
                "manifest": {
                    "id": "campaign:published",
                    "session_id": "campaign:published",
                    "schema_version": "rpg-session-v1",
                },
                "state": {"title": "Published Campaign"},
                "runtime_state": {},
                "setup_payload": {},
            },
        },
    )
    monkeypatch.setattr(
        "app.rpg.worlds.published_launch.save_session",
        lambda session, **_kwargs: session,
    )

    class FakeRpg:
        def get_campaign(self, *_args, **_kwargs):
            return None

        def create_campaign(self, _context, **kwargs):
            captured["campaign"] = kwargs
            return kwargs

    class FakeWorldScenarios:
        def get_world(self, *_args, **_kwargs):
            return {
                "id": "world:published",
                "genre": "classic_fantasy",
                "tone": "heroic adventure",
                "seed": 7,
            }

        def bind_campaign(self, _context, **kwargs):
            captured["binding"] = kwargs
            return kwargs["binding"]

    class FakeMapInstances:
        def create_instance(self, _context, **kwargs):
            captured["map_instance"] = kwargs
            return kwargs

    class FakeWork:
        def __init__(self):
            self.rpg = FakeRpg()
            self.world_scenarios = FakeWorldScenarios()
            self.map_instances = FakeMapInstances()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            captured["committed"] = True

        def rollback(self):
            captured["rolled_back"] = True

    def fake_schedule(campaign_id: str, **kwargs):
        captured["materialization_signal"] = {
            "campaign_id": campaign_id,
            **kwargs,
        }
        return {
            "ok": True,
            "status": "not_applicable",
            "scheduled": [],
            "worker_started": False,
        }

    monkeypatch.setattr(
        "app.rpg.worlds.published_launch.unit_of_work",
        lambda _database: FakeWork(),
    )
    monkeypatch.setattr(
        "app.rpg.worlds.published_launch.schedule_campaign_predictive_materialization",
        fake_schedule,
    )

    result = launch_published_scenario(
        world_id="world:published",
        world_revision=1,
        world_release=1,
        scenario_id="scenario:opening",
        scenario_revision=1,
        player={"name": "Alyndra"},
    )

    assert result["ok"] is True
    assert result["session_id"] == "campaign:published"
    assert result["launch_mode"] == "published_scenario"
    assert result["world_forge_invoked"] is False
    assert result["materialization_schedule"]["status"] == "not_applicable"
    assert captured["materialization_signal"] == {
        "campaign_id": "campaign:published",
        "current_location_id": "rusty_flagon_tavern",
        "database": None,
        "kick_worker": True,
        "allow_missing_plan": True,
    }
    assert (
        result["session"]["state"]["world_binding"]["world_revision_hash"]
        == world_revision.content_hash
    )
    assert (
        result["session"]["state"]["world_binding"]["world_release_hash"]
        == release.release_hash
    )
    assert (
        result["session"]["state"]["world_binding"]["scenario_revision_hash"]
        == scenario.content_hash
    )
    assert result["session"]["state"]["current_map_instance_id"] == (
        "campaign:published:map:map:rusty_flagon:1"
    )
    snapshot = captured["map_instance"]["snapshot"]
    assert snapshot["actors"][0]["actor_id"] == "player:campaign:published"
    assert snapshot["actors"][0]["cell"] == [1, 1]
    assert captured["binding"]["campaign_id"] == "campaign:published"
    assert captured["campaign"]["metadata"]["launch_mode"] == "published_scenario"
    assert captured["campaign"]["metadata"]["starting_map_instance_id"] == (
        "campaign:published:map:map:rusty_flagon:1"
    )
    assert captured["committed"] is True
