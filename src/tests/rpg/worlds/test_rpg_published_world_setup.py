"""A published world becomes the turn engine's world: places, people, routes, kit and quests (no database)."""
from __future__ import annotations

from types import SimpleNamespace

from app.apps.rpg.genesis.worlds.published_world_setup import (
    creator_setup,
    location_label,
    opening_kit,
    opening_quests,
    session_world_model,
)
from app.apps.rpg.rules import location_registry
from app.apps.rpg.world.travel_graph import (
    apply_travel_result_to_state,
    list_available_routes,
    resolve_travel_destination,
)

REVISION = SimpleNamespace(
    world_id="world:glass",
    revision=2,
    title="The Glass Coast",
    canon={
        "summary": "A coast of glass dunes.",
        "regions": [{"id": "region:shore", "name": "The Shore", "summary": "Wind and salt glass"}],
        "characters": [
            {"id": "npc:ada", "name": "Ada Vell", "role": "tide warden", "biography": "Ada walks the Glass Strand."},
            {"id": "npc:bo", "name": "Bo Kett", "role": "innkeeper of the Salt Lamp", "biography": "Bo keeps the Salt Lamp."},
            {"id": "npc:cy", "name": "Cy", "role": "wanderer", "biography": "Nobody knows where."},
        ],
        "items": [{"id": "item:shard", "name": "Sea Shard", "type": "relic", "effect": "hums near water"}],
        "quests": [
            {"id": "quest:first-tide", "title": "First Tide", "tier": "intro", "objective": "Reach the Salt Lamp",
             "locations": ["location:strand"]},
            {"id": "quest:drowned-bell", "title": "The Drowned Bell", "objective": "Find the bell"},
        ],
        "factions": [{"id": "faction:wardens", "name": "Tide Wardens", "agenda": "Hold back the sea"}],
    },
    entity_manifest={"locations": ["location:strand", "location:salt-lamp", "location:lighthouse"]},
    topology={
        "locations": [
            {"id": "location:strand", "name": "Glass Strand", "region_id": "region:shore"},
            {"id": "location:salt-lamp", "name": "Salt Lamp", "region_id": "region:shore"},
        ],
        "routes": [{"id": "route:1", "from": "location:strand", "to": "location:salt-lamp", "travel_time": "90 minutes"}],
    },
    adventure_seeds=({"id": "seed:bell", "quest_id": "quest:drowned-bell", "hook": "A bell rings under the waves."},),
)
SCENARIO = SimpleNamespace(
    starting_location_id="location:strand",
    starting_epoch="Day 1, 07:00",
    initial_npc_ids=("npc:ada", "npc:bo"),
    opening_seed_ids=("seed:bell",),
    starting_resources={
        "currency": {"silver": 3, "copper": 7},
        "inventory": ["item:shard", "item:shard"],
        "stats": {"health": 80, "aether": 25},
    },
)


def _model() -> dict:
    return session_world_model(REVISION, SCENARIO, present_at_start=("npc:ada",))


def test_world_model_places_people_routes_and_services() -> None:
    model = _model()
    strand, lamp = model["locations"]["location:strand"], model["locations"]["location:salt-lamp"]
    assert strand["name"] == "Glass Strand" and strand["region_name"] == "The Shore"
    assert "The Shore" in strand["description"]
    # On the opening's map at the start; the innkeeper where their story names; the wanderer nowhere.
    assert [npc["name"] for npc in strand["present_npcs"]] == ["Ada Vell"]
    assert [npc["name"] for npc in lamp["present_npcs"]] == ["Bo Kett"]
    assert model["npcs"]["npc:cy"]["location_id"] == ""
    assert lamp["services"] == ["lodging", "meal"]
    assert strand["exits"] == {"salt lamp": "location:salt-lamp"}
    assert model["locations"]["location:lighthouse"]["name"] == "Lighthouse"
    assert location_label(REVISION, "location:lighthouse") == "Lighthouse"


def test_creator_setup_replaces_the_starter_town() -> None:
    setup = creator_setup(REVISION, SCENARIO, _model(), {"genre": "fantasy"})
    assert setup["starting_location_id"] == "location:strand"
    assert setup["starting_npc_ids"] == ["npc:ada"]
    assert {row["location_id"] for row in setup["locations"]} == {
        "location:strand", "location:salt-lamp", "location:lighthouse",
    }
    assert {row["name"] for row in setup["npc_seeds"]} == {"Ada Vell", "Bo Kett", "Cy"}
    assert setup["factions"][0]["name"] == "Tide Wardens"


def test_opening_kit_and_quests() -> None:
    kit = opening_kit(
        REVISION,
        SCENARIO,
        equipment=[{"slot": "Weapon", "name": "Iron Dagger"}],
        inventory=[{"id": "iron_dagger", "name": "Iron Dagger", "quantity": 1}, {"id": "torch", "name": "Torch", "quantity": 2}],
    )
    assert [(item["name"], item["quantity"]) for item in kit["inventory"]] == [("Iron Dagger", 1), ("Sea Shard", 2)]
    assert kit["inventory"][1]["description"] == "hums near water"
    assert kit["currency"] == {"gold": 0, "silver": 3, "copper": 7}
    assert (kit["health"], kit["aether"]) == (80, 25)
    quests = opening_quests(REVISION, SCENARIO)
    assert [(quest["title"], quest["status"]) for quest in quests] == [
        ("First Tide", "active"), ("The Drowned Bell", "available"),
    ]
    assert quests[1]["hook"] == "A bell rings under the waves."


def test_registry_and_travel_use_the_session_world() -> None:
    simulation = {"world_model": _model(), "player_state": {"location_id": "location:strand"}}
    assert location_registry.current_location_id(simulation) == "location:strand"
    assert [npc["name"] for npc in location_registry.present_npcs_for_current_location(simulation)] == ["Ada Vell"]
    assert location_registry.find_location_by_name("the salt lamp", simulation)["location_id"] == "location:salt-lamp"
    # A world-model session never falls back to the starter town's places.
    assert location_registry.find_location_by_name("market", simulation) == {}
    assert location_registry.default_location_id({"world_model": _model()}) == "location:strand"

    state = {**simulation, "current_location_id": "location:strand"}
    assert [route["to_name"] for route in list_available_routes(state=state)] == ["Salt Lamp"]
    travel = resolve_travel_destination(player_input="walk to the Salt Lamp", state=state)
    assert travel["ok"] and travel["to_location"] == "location:salt-lamp"
    assert travel["travel_time_ticks"] == 2
    moved = apply_travel_result_to_state(state=state, travel_result=travel)
    assert moved["player_state"]["location_id"] == "location:salt-lamp"
    assert location_registry.current_location_id(moved) == "location:salt-lamp"
    assert location_registry.location_allows_service(moved, "meal")


def test_sessions_without_a_world_keep_the_starter_town() -> None:
    assert location_registry.current_location_id({}) == "loc_tavern"
    assert location_registry.find_location_by_name("market")["location_id"] == "loc_market"
    routes = list_available_routes(state={"current_location": "location:rusty_flagon_tavern"})
    assert routes and routes[0]["from_location"] == "location:rusty_flagon_tavern"
