from app.rpg.session.genesis.world_forge_planning import (
    PlanningTopicDefinition,
    planning_contract_metadata,
    planning_revision_hash,
    planning_slice_for_topic,
    planning_topic_definitions,
    validate_planning_contract,
)
from app.rpg.session.genesis.world_forge_profile_generation import (
    default_profile_registry,
)
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_topic_graph


def test_planning_contract_is_internal_revisioned_and_acyclic() -> None:
    definitions = planning_topic_definitions()
    metadata = planning_contract_metadata()

    assert validate_planning_contract(definitions) == ()
    assert metadata["schema_version"] == "rpg_world_forge_planning_contract_v1"
    assert metadata["revision_hash"] == planning_revision_hash(definitions)
    assert metadata["internal"] is True
    assert metadata["publish_as_authoring_pages"] is False
    assert all(row["internal"] for row in metadata["topics"])
    assert not any(row["publish_as_authoring_page"] for row in metadata["topics"])


def test_planning_slices_are_selective_not_universal() -> None:
    planning_topics = {
        definition.topic_id: {"topic_id": definition.topic_id}
        for definition in planning_topic_definitions()
    }

    actor_slice = planning_slice_for_topic("actors", planning_topics)
    region_slice = planning_slice_for_topic("regions", planning_topics)

    assert "anchor_registry" in actor_slice
    assert "political_claim_graph" in actor_slice
    assert "geography_resource_plan" not in actor_slice
    assert "geography_resource_plan" in region_slice
    assert "pressure_plan" not in region_slice
    assert set(actor_slice) != set(planning_topics)


def test_planning_hash_is_stable_and_changes_with_revision() -> None:
    definitions = planning_topic_definitions()
    changed = (
        PlanningTopicDefinition(
            definitions[0].topic_id,
            dependencies=definitions[0].dependencies,
            consumers=definitions[0].consumers,
            revision=definitions[0].revision + 1,
        ),
        *definitions[1:],
    )

    assert planning_revision_hash() == planning_revision_hash()
    assert planning_revision_hash(changed) != planning_revision_hash(definitions)


def test_profile_graph_records_planning_contract_without_planning_nodes() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(
        profile,
        campaign_template="planning-contract",
        depth="quick",
    )

    assert graph.metadata["planning_contract"] == planning_contract_metadata()
    assert not set(definition.topic_id for definition in planning_topic_definitions()) & set(
        graph.node_map()
    )
