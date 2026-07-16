from __future__ import annotations

from typing import Any

from app.rpg.worlds.published_launch import launch_published_scenario
from app.rpg.worlds.service import (
    compile_scenario_revision,
    compile_world_release,
    compile_world_revision,
)


def test_published_scenario_launch_creates_bound_campaign_without_world_forge(
    monkeypatch,
) -> None:
    world_revision = compile_world_revision(
        world_id="world:published",
        revision=1,
        title="Published World",
        canon={"campaign_template": "classic_fantasy"},
        entity_manifest={},
        topology={"locations": ["rusty_flagon_tavern"], "routes": []},
    )
    release = compile_world_release(
        world_revision,
        release=1,
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

    class FakeWork:
        def __init__(self):
            self.rpg = FakeRpg()
            self.world_scenarios = FakeWorldScenarios()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            captured["committed"] = True

        def rollback(self):
            captured["rolled_back"] = True

    monkeypatch.setattr(
        "app.rpg.worlds.published_launch.unit_of_work",
        lambda _database: FakeWork(),
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
    assert result["session"]["state"]["world_binding"]["world_revision_hash"] == world_revision.content_hash
    assert result["session"]["state"]["world_binding"]["world_release_hash"] == release.release_hash
    assert result["session"]["state"]["world_binding"]["scenario_revision_hash"] == scenario.content_hash
    assert captured["binding"]["campaign_id"] == "campaign:published"
    assert captured["campaign"]["metadata"]["launch_mode"] == "published_scenario"
    assert captured["committed"] is True
