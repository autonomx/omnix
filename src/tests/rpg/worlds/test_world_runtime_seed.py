from app.rpg.worlds.contracts import canonical_content_hash
from app.rpg.worlds.runtime_seed import (
    compile_runtime_seed,
    compile_vertical_slice,
    run_player_absent_playtest,
)


def _profile() -> dict:
    return {
        "profile_id": "test_profile",
        "version": 1,
        "domains": [
            {
                "domain_id": "places",
                "entity_kind": "place",
                "semantic_roles": ["starting_context"],
            },
            {
                "domain_id": "groups",
                "entity_kind": "group",
                "semantic_roles": ["initial_conflict"],
            },
            {
                "domain_id": "actors",
                "entity_kind": "actor",
                "semantic_roles": ["initial_actors"],
            },
            {
                "domain_id": "pressures",
                "entity_kind": "pressure",
                "semantic_roles": ["initial_conflict"],
            },
            {
                "domain_id": "opening_threads",
                "entity_kind": "opening_thread",
                "semantic_roles": [],
            },
            {
                "domain_id": "survival_resources",
                "entity_kind": "resource_system",
                "semantic_roles": [],
            },
        ],
    }


def _canon() -> dict:
    entities: dict[str, dict] = {}
    for index in range(3):
        entities[f"place:{index}"] = {
            "id": f"place:{index}",
            "kind": "place",
            "name": f"Harbor Place {index}",
        }
        entities[f"group:{index}"] = {
            "id": f"group:{index}",
            "kind": "group",
            "name": f"Harbor Group {index}",
            "current_objective": f"Secure relay corridor {index} before the evening tide.",
            "next_action": f"Dispatch survey crew {index} at dawn.",
            "dependencies": {"resource": f"resource:{index}"},
            "failure_response": f"Close ferry route {index} and ration power.",
        }
        entities[f"actor:{index}"] = {
            "id": f"actor:{index}",
            "kind": "actor",
            "name": f"Harbor Actor {index}",
            "location_id": f"place:{index}",
            "group_ids": [f"group:{index}"],
            "goal": f"Restore beacon {index} before the storm front arrives.",
            "dependency": f"Needs calibrated relay housing {index}.",
            "next_action": f"Inspect beacon {index} at first light.",
            "reaction_conditions": {"blocked": f"Report to group:{index}"},
        }
        entities[f"pressure:{index}"] = {
            "id": f"pressure:{index}",
            "kind": "pressure",
            "name": f"Tidal Pressure {index}",
            "actor_ids": [f"actor:{index}"],
            "group_ids": [f"group:{index}"],
            "place_ids": [f"place:{index}"],
            "current_state": f"Warning marker {index} is already submerged.",
            "next_tick_change": f"Water reaches workshop level {index} tomorrow.",
            "escalation_condition": f"Escalates when pump {index} stops for one hour.",
        }
        entities[f"opening:{index}"] = {
            "id": f"opening:{index}",
            "kind": "opening_thread",
            "name": f"Opening Thread {index}",
            "place_ids": [f"place:{index}"],
            "actor_ids": [f"actor:{index}"],
        }
    entities["resource:water"] = {
        "id": "resource:water",
        "kind": "resource_system",
        "name": "Clean Water Reserve",
        "state": {"quality": "filtered"},
        "quantity": 14,
        "consumption_per_day": 1,
        "controller_group_ids": ["group:0"],
    }
    return {
        "topic_graph": {
            "metadata": {
                "resolved_profile": _profile(),
                "resolved_profile_hash": "sha256:profile",
                "runtime_capabilities": {
                    "living_world": True,
                    "resource_simulation": True,
                },
            }
        },
        "entities": entities,
    }


def test_runtime_seed_and_vertical_slice_are_playtest_ready() -> None:
    canon = _canon()
    canon_hash = canonical_content_hash(canon)
    runtime_seed = compile_runtime_seed(
        world_id="world:harbor",
        world_revision=1,
        source_canon_hash=canon_hash,
        canon=canon,
        seed=17,
    )
    assert runtime_seed.passed
    assert len(runtime_seed.agents) == 6
    assert len(runtime_seed.clocks) == 3
    assert len(runtime_seed.resources) == 1
    assert runtime_seed.resources[0].daily_delta == -1

    materialization = compile_vertical_slice(
        runtime_seed=runtime_seed,
        canon=canon,
        starting_location="place:0",
    )
    assert materialization.passed, materialization.checks
    assert materialization.hub_location_id == "place:0"
    assert len(materialization.actor_ids) == 3
    assert len(materialization.group_ids) == 3
    assert len(materialization.clock_ids) == 3

    playtest = run_player_absent_playtest(runtime_seed, days=7)
    assert playtest.passed, playtest.checks
    assert playtest.direct_final_state_hash == playtest.reloaded_final_state_hash
    assert len(playtest.daily_events) == 7


def test_unknown_explicit_starting_location_does_not_fallback() -> None:
    canon = _canon()
    runtime_seed = compile_runtime_seed(
        world_id="world:harbor",
        world_revision=1,
        source_canon_hash=canonical_content_hash(canon),
        canon=canon,
    )
    materialization = compile_vertical_slice(
        runtime_seed=runtime_seed,
        canon=canon,
        starting_location="place:missing",
    )
    assert materialization.passed is False
    assert materialization.hub_location_id == ""
    assert materialization.checks["starting_location_resolved"] is False
