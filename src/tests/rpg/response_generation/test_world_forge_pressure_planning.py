from app.rpg.session.genesis.world_forge_anchor_registry import (
    allocate_global_anchor_registry,
)
from app.rpg.session.genesis.world_forge_historical_planning import (
    build_historical_planning_topics,
)
from app.rpg.session.genesis.world_forge_pressure_planning import (
    build_opening_scope_plan,
    build_pressure_plan,
    build_pressure_planning_topics,
)
from app.rpg.session.genesis.world_forge_profile_generation import (
    default_profile_registry,
)
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_topic_graph
from app.rpg.session.genesis.world_forge_social_planning import (
    build_social_planning_topics,
)


def _inputs(seed: int = 29):
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(
        profile,
        campaign_template="pressure-planning",
        depth="quick",
    )
    registry = allocate_global_anchor_registry(
        graph,
        seed=seed,
        world_key="campaign:pressure",
    )
    historical = build_historical_planning_topics(
        registry,
        seed=seed,
        world_key="campaign:pressure",
    )
    social = build_social_planning_topics(
        registry,
        historical["geography_resource_plan"],
        historical["historical_epoch_plan"],
        historical["present_day_state"],
        seed=seed,
    )
    return registry, historical, social


def test_pressure_plan_is_anchor_safe_and_actionable() -> None:
    registry, historical, social = _inputs()
    plan = build_pressure_plan(
        registry,
        historical["present_day_state"],
        social["political_claim_graph"],
        social["settlement_origin_plan"],
        seed=29,
    )
    region_ids = {
        row["id"] for row in registry["anchors"] if row["domain_id"] == "regions"
    }
    place_ids = {
        row["id"] for row in registry["anchors"] if row["domain_id"] == "places"
    }
    group_ids = {
        row["id"] for row in registry["anchors"] if row["domain_id"] == "groups"
    }

    assert plan["pressures"]
    for row in plan["pressures"]:
        assert set(row["affected_region_ids"]) <= region_ids
        assert set(row["affected_place_ids"]) <= place_ids
        assert set(row["affected_group_ids"]) <= group_ids
        assert 0 <= row["severity"] <= 100
        assert row["next_tick_delta"]["operation"] == "decrease"
        assert row["resolution_threshold"] <= row["severity"] <= row["escalation_threshold"]


def test_opening_scope_uses_highest_severity_pressures() -> None:
    registry, historical, social = _inputs()
    pressure = build_pressure_plan(
        registry,
        historical["present_day_state"],
        social["political_claim_graph"],
        social["settlement_origin_plan"],
        seed=29,
    )
    opening = build_opening_scope_plan(
        registry,
        pressure,
        seed=29,
        maximum_pressures=2,
    )
    ranked = sorted(
        pressure["pressures"],
        key=lambda row: (-row["severity"], row["pressure_id"]),
    )[:2]

    assert opening["pressure_ids"] == [row["pressure_id"] for row in ranked]
    assert len(opening["thread_slots"]) == len(ranked)
    assert all(row["initial_visibility"] == "local_observable" for row in opening["thread_slots"])


def test_pressure_planning_bundle_is_reproducible_and_complete() -> None:
    registry, historical, social = _inputs(seed=31)
    first = build_pressure_planning_topics(
        registry,
        historical["present_day_state"],
        social["political_claim_graph"],
        social["settlement_origin_plan"],
        seed=31,
    )
    second = build_pressure_planning_topics(
        registry,
        historical["present_day_state"],
        social["political_claim_graph"],
        social["settlement_origin_plan"],
        seed=31,
    )

    assert first == second
    assert set(first) == {"pressure_plan", "opening_scope_plan"}
    assert first["opening_scope_plan"]["pressure_plan_hash"] == first["pressure_plan"]["content_hash"]
