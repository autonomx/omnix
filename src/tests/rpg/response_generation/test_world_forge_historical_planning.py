from app.rpg.session.genesis.world_forge_anchor_registry import (
    allocate_global_anchor_registry,
)
from app.rpg.session.genesis.world_forge_historical_planning import (
    apply_historical_deltas,
    build_geography_resource_plan,
    build_historical_epoch_plan,
    build_historical_planning_topics,
    build_present_day_state,
)
from app.rpg.session.genesis.world_forge_profile_generation import (
    default_profile_registry,
)
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_topic_graph


def _graph():
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    return build_profile_topic_graph(
        profile,
        campaign_template="historical-planning",
        depth="quick",
    )


def _registry(seed: int = 11):
    return allocate_global_anchor_registry(
        _graph(),
        seed=seed,
        world_key="campaign:history",
    )


def test_geography_plan_is_deterministic_and_anchor_bound() -> None:
    registry = _registry()
    first = build_geography_resource_plan(registry, seed=11)
    second = build_geography_resource_plan(registry, seed=11)

    assert first == second
    assert first["anchor_registry_hash"] == registry["registry_hash"]
    region_ids = {
        row["id"]
        for row in registry["anchors"]
        if row["domain_id"] == "regions"
    }
    assert {row["region_id"] for row in first["regions"]} == region_ids
    assert all(0 <= row["strategic_value"] <= 100 for row in first["regions"])
    assert all(row["settlement_capacity"] >= 1 for row in first["regions"])


def test_historical_epochs_form_a_contiguous_state_chain() -> None:
    registry = _registry()
    geography = build_geography_resource_plan(registry, seed=11)
    history = build_historical_epoch_plan(
        registry,
        geography,
        seed=11,
        era_count=4,
    )

    assert [row["sequence"] for row in history["epochs"]] == [1, 2, 3, 4]
    assert history["epochs"][0]["start_state"] == history["initial_state"]
    for previous, current in zip(history["epochs"], history["epochs"][1:]):
        assert current["start_state"] == previous["end_state"]
    assert all(
        event["year"] >= 100
        for era in history["epochs"]
        for event in era["events"]
    )


def test_typed_historical_deltas_are_pure_and_clamped() -> None:
    state = {
        "ent:regions:001": {
            "population_index": 95,
            "trade_access": 20,
            "political_stability": 50,
        }
    }
    result = apply_historical_deltas(
        state,
        (
            {
                "target_id": "ent:regions:001",
                "dimension": "population_index",
                "operation": "increase",
                "value": 20,
            },
            {
                "target_id": "ent:regions:001",
                "dimension": "trade_access",
                "operation": "decrease",
                "value": 30,
            },
            {
                "target_id": "ent:regions:001",
                "dimension": "political_stability",
                "operation": "replace",
                "value": 72,
            },
        ),
    )

    assert state["ent:regions:001"]["population_index"] == 95
    assert result["ent:regions:001"]["population_index"] == 100
    assert result["ent:regions:001"]["trade_access"] == 0
    assert result["ent:regions:001"]["political_stability"] == 72


def test_present_day_state_is_exact_final_epoch_reduction() -> None:
    registry = _registry()
    geography = build_geography_resource_plan(registry, seed=11)
    history = build_historical_epoch_plan(registry, geography, seed=11)
    present = build_present_day_state(history)

    assert present["historical_plan_hash"] == history["content_hash"]
    assert present["state"] == history["epochs"][-1]["end_state"]


def test_historical_planning_bundle_is_reproducible_and_complete() -> None:
    registry = _registry(seed=13)
    first = build_historical_planning_topics(
        registry,
        seed=13,
        world_key="campaign:bundle",
    )
    second = build_historical_planning_topics(
        registry,
        seed=13,
        world_key="campaign:bundle",
    )

    assert first == second
    assert set(first) == {
        "world_invariants",
        "geography_resource_plan",
        "historical_epoch_plan",
        "present_day_state",
    }
    assert first["world_invariants"]["invariants"]["prose_cannot_mutate_state"] is True
