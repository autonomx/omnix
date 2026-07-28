from app.rpg.session.genesis.world_forge_anchor_registry import (
    allocate_global_anchor_registry,
)
from app.rpg.session.genesis.world_forge_historical_planning import (
    build_historical_planning_topics,
)
from app.rpg.session.genesis.world_forge_profile_generation import (
    default_profile_registry,
)
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_topic_graph
from app.rpg.session.genesis.world_forge_social_planning import (
    build_culture_lineage_plan,
    build_political_claim_graph,
    build_settlement_origin_plan,
    build_social_planning_topics,
)


def _inputs(seed: int = 19):
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(
        profile,
        campaign_template="social-planning",
        depth="quick",
    )
    registry = allocate_global_anchor_registry(
        graph,
        seed=seed,
        world_key="campaign:social",
    )
    historical = build_historical_planning_topics(
        registry,
        seed=seed,
        world_key="campaign:social",
    )
    return registry, historical


def test_political_claims_reference_only_allocated_groups_and_regions() -> None:
    registry, historical = _inputs()
    graph = build_political_claim_graph(
        registry,
        historical["present_day_state"],
        seed=19,
    )
    groups = {
        row["id"] for row in registry["anchors"] if row["domain_id"] == "groups"
    }
    regions = {
        row["id"] for row in registry["anchors"] if row["domain_id"] == "regions"
    }

    assert graph["claims"]
    assert {row["claimant_group_id"] for row in graph["claims"]} <= groups
    assert {row["target_region_id"] for row in graph["claims"]} <= regions
    assert all(0 <= row["legitimacy"] <= 100 for row in graph["claims"])
    assert all(0 <= row["control_index"] <= 100 for row in graph["claims"])


def test_settlement_origins_bind_places_to_geography_and_history() -> None:
    registry, historical = _inputs()
    plan = build_settlement_origin_plan(
        registry,
        historical["geography_resource_plan"],
        historical["historical_epoch_plan"],
        seed=19,
    )
    place_ids = {
        row["id"] for row in registry["anchors"] if row["domain_id"] == "places"
    }
    region_ids = {
        row["id"] for row in registry["anchors"] if row["domain_id"] == "regions"
    }
    event_ids = {
        event["event_id"]
        for era in historical["historical_epoch_plan"]["epochs"]
        for event in era["events"]
    }

    assert {row["place_id"] for row in plan["settlements"]} == place_ids
    assert {row["region_id"] for row in plan["settlements"]} <= region_ids
    assert {row["founding_event_id"] for row in plan["settlements"]} <= event_ids
    assert all(row["route_dependency"] >= 0 for row in plan["settlements"])


def test_culture_lineages_are_acyclic_by_construction() -> None:
    registry, historical = _inputs()
    plan = build_culture_lineage_plan(
        registry,
        historical["historical_epoch_plan"],
        historical["present_day_state"],
        seed=19,
    )
    order = {row["culture_id"]: index for index, row in enumerate(plan["lineages"])}

    for row in plan["lineages"]:
        parent = row["parent_culture_id"]
        assert not parent or order[parent] < order[row["culture_id"]]
        assert 0 <= row["cohesion_index"] <= 100


def test_social_planning_bundle_is_reproducible_and_complete() -> None:
    registry, historical = _inputs(seed=23)
    first = build_social_planning_topics(
        registry,
        historical["geography_resource_plan"],
        historical["historical_epoch_plan"],
        historical["present_day_state"],
        seed=23,
    )
    second = build_social_planning_topics(
        registry,
        historical["geography_resource_plan"],
        historical["historical_epoch_plan"],
        historical["present_day_state"],
        seed=23,
    )

    assert first == second
    assert set(first) == {
        "political_claim_graph",
        "settlement_origin_plan",
        "culture_lineage_plan",
    }
