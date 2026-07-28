from app.rpg.session.genesis.world_forge_anchor_registry import (
    allocate_global_anchor_registry,
)
from app.rpg.session.genesis.world_forge_historical_planning import (
    build_historical_planning_topics,
)
from app.rpg.session.genesis.world_forge_pressure_planning import (
    build_pressure_planning_topics,
)
from app.rpg.session.genesis.world_forge_profile_generation import (
    default_profile_registry,
)
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_topic_graph
from app.rpg.session.genesis.world_forge_social_planning import (
    build_social_planning_topics,
)
from app.rpg.world.causal_state import (
    build_mutable_world_state,
    mutable_dimension_registry,
    validate_mutable_world_state,
)


def _planning_topics(seed: int = 37):
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(
        profile,
        campaign_template="mutable-state",
        depth="quick",
    )
    registry = allocate_global_anchor_registry(
        graph,
        seed=seed,
        world_key="campaign:mutable",
    )
    historical = build_historical_planning_topics(
        registry,
        seed=seed,
        world_key="campaign:mutable",
    )
    social = build_social_planning_topics(
        registry,
        historical["geography_resource_plan"],
        historical["historical_epoch_plan"],
        historical["present_day_state"],
        seed=seed,
    )
    pressure = build_pressure_planning_topics(
        registry,
        historical["present_day_state"],
        social["political_claim_graph"],
        social["settlement_origin_plan"],
        seed=seed,
    )
    return {
        "anchor_registry": registry,
        **historical,
        **social,
        **pressure,
    }


def test_mutable_dimension_registry_has_unique_scoped_dimensions() -> None:
    registry = mutable_dimension_registry()

    assert len({row.dimension_id for row in registry}) == len(registry)
    assert {row.target_kind for row in registry} == {
        "region",
        "claim",
        "settlement",
        "culture",
        "pressure",
    }
    assert all(row.minimum <= row.default <= row.maximum for row in registry)


def test_mutable_state_is_deterministic_typed_and_bounded() -> None:
    planning = _planning_topics()
    first = build_mutable_world_state(planning)
    second = build_mutable_world_state(planning)

    assert first == second
    assert validate_mutable_world_state(first) == ()
    assert first["schema_version"] == "rpg_causal_world_state_v1"
    assert first["tick"] == 0
    assert first["event_cursor"] == 0
    assert first["state_hash"].startswith("sha256:")
    for cell in first["cells"].values():
        assert cell["revision"] == 1
        assert all(0 <= value <= 100 for value in cell["values"].values())


def test_mutable_state_materialises_all_planned_target_kinds() -> None:
    state = build_mutable_world_state(_planning_topics())
    kinds = {cell["target_kind"] for cell in state["cells"].values()}

    assert kinds == {"region", "claim", "settlement", "culture", "pressure"}
    assert any(
        "political_stability" in cell["values"]
        for cell in state["cells"].values()
        if cell["target_kind"] == "region"
    )
    assert any(
        "pressure_severity" in cell["values"]
        for cell in state["cells"].values()
        if cell["target_kind"] == "pressure"
    )


def test_mutable_state_validation_rejects_scope_mismatch() -> None:
    state = build_mutable_world_state(_planning_topics())
    pressure_id = next(
        target_id
        for target_id, cell in state["cells"].items()
        if cell["target_kind"] == "pressure"
    )
    state["cells"][pressure_id]["values"] = {"trade_access": 50}

    assert validate_mutable_world_state(state) == (
        f"mutable_state_dimension_scope_mismatch:{pressure_id}:trade_access",
    )
