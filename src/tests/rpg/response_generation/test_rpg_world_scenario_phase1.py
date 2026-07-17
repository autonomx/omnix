from __future__ import annotations

from fastapi import FastAPI

from app.gateway.rpg_world_routes import register_rpg_world_routes
from app.rpg.session.genesis.contract import CampaignGenesisContract
from app.rpg.worlds.contracts import (
    MapDefinitionBinding,
    MapInitializationOperation,
)
from app.rpg.worlds.legacy_adapter import adapt_campaign_genesis_to_world_launch
from app.rpg.worlds.service import (
    compile_scenario_revision,
    compile_world_release,
    compile_world_revision,
    resolve_campaign_binding,
)


def _world_revision():
    return compile_world_revision(
        world_id="world:ashen_coast",
        revision=1,
        title="Ashen Coast",
        canon={"realm": {"name": "Ashen Coast"}},
        entity_manifest={
            "locations": [
                {"id": "location:black_tide_harbor", "kind": "settlement"}
            ]
        },
        topology={"locations": ["location:black_tide_harbor"], "routes": []},
        adventure_seeds=[{"id": "seed:vanished_lighthouse"}],
        blueprint_requirements=[{"map_id": "settlement:black_tide_harbor"}],
        provenance={"source": "manual_test"},
    )


def test_world_release_scenario_and_campaign_binding_are_exactly_pinned() -> None:
    world = _world_revision()
    release = compile_world_release(
        world,
        release=1,
        map_bindings=[
            MapDefinitionBinding(
                map_id="settlement:black_tide_harbor",
                blueprint_revision=1,
                definition_revision=1,
                definition_hash="sha256:" + "a" * 64,
                semantic_interface_hash="sha256:" + "b" * 64,
                simulation_readiness="certified",
                presentation_readiness="assets_pending",
            )
        ],
        certification={"passed": True},
    )
    scenario = compile_scenario_revision(
        scenario_id="scenario:after_the_war",
        revision=1,
        world_revision=world,
        compatible_release=1,
        starting_epoch="year_418_spring",
        starting_location_id="location:black_tide_harbor",
        activated_conflict_ids=["conflict:succession_crisis"],
        opening_seed_ids=["seed:vanished_lighthouse"],
        map_initialization=[
            MapInitializationOperation(
                operation_id="init:close_east_gate",
                map_id="settlement:black_tide_harbor",
                type="set_object_state",
                target_id="gate:eastern",
                payload={"state": "closed"},
            )
        ],
    )
    binding = resolve_campaign_binding(
        campaign_id="campaign:a",
        world_revision=world,
        world_release=release,
        scenario_revision=scenario,
    )

    assert world.content_hash.startswith("sha256:")
    assert release.world_revision_hash == world.content_hash
    assert release.release_hash.startswith("sha256:")
    assert scenario.world_revision_hash == world.content_hash
    assert scenario.content_hash.startswith("sha256:")
    assert binding.world_revision == 1
    assert binding.world_release == 1
    assert binding.scenario_revision == 1
    assert binding.map_definition_pins == {
        "settlement:black_tide_harbor": "sha256:" + "a" * 64
    }


def test_scenario_release_policy_rejects_implicit_upgrade() -> None:
    world = _world_revision()
    release = compile_world_release(world, release=2)
    scenario = compile_scenario_revision(
        scenario_id="scenario:after_the_war",
        revision=1,
        world_revision=world,
        compatible_release=1,
        starting_location_id="location:black_tide_harbor",
    )

    try:
        resolve_campaign_binding(
            campaign_id="campaign:a",
            world_revision=world,
            world_release=release,
            scenario_revision=scenario,
        )
    except ValueError as exc:
        assert str(exc) == "scenario_release_incompatible"
    else:
        raise AssertionError("incompatible release must not be selected")


def test_legacy_genesis_adapter_separates_world_scenario_and_campaign() -> None:
    legacy = CampaignGenesisContract.model_validate(
        {
            "campaign_template": "classic_fantasy",
            "tone": "grim coastal fantasy",
            "identity": {"name": "Elara"},
            "world_options": {
                "starting_location": "rusty_flagon_tavern",
                "seed": 42,
            },
        }
    )
    adapted = adapt_campaign_genesis_to_world_launch(
        legacy,
        campaign_id="campaign:legacy",
    )

    assert adapted.world.world_id == "world:legacy:campaign:legacy"
    assert adapted.scenario.world_id == adapted.world.world_id
    assert adapted.campaign.world_id == adapted.world.world_id
    assert adapted.campaign.protagonist["identity"]["name"] == "Elara"
    assert adapted.legacy_payload_hash.startswith("sha256:")


def test_world_routes_register_separate_resource_endpoints() -> None:
    app = FastAPI()
    register_rpg_world_routes(app)
    paths = {route.path for route in app.routes}

    assert "/api/rpg/worlds" in paths
    assert "/api/rpg/worlds/{world_id}/archive" in paths
    assert "/api/rpg/worlds/{world_id}/restore" in paths
    assert "/api/rpg/worlds/{world_id}/topic-history" in paths
    assert "/api/rpg/worlds/{world_id}/drafts/{source_draft_revision}/restore" in paths
    assert "/api/rpg/worlds/{world_id}/revisions" in paths
    assert (
        "/api/rpg/worlds/{world_id}/revisions/{world_revision}/releases" in paths
    )
    assert "/api/rpg/scenarios" in paths
    assert "/api/rpg/scenarios/{scenario_id}/archive" in paths
    assert "/api/rpg/scenarios/{scenario_id}/restore" in paths
    assert "/api/rpg/scenarios/{scenario_id}/revisions" in paths
    assert "/api/rpg/campaigns/{campaign_id}/legacy-world-import" in paths
    assert "/api/rpg/campaigns/{campaign_id}/world-binding" in paths
