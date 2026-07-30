from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.worlds.generation_entity_manifest import (
    EntityManifestContractError,
    build_entity_manifest,
    topic_manifest_slots,
)


def _graph() -> CampaignTopicGraph:
    return CampaignTopicGraph(
        graph_version="entity-manifest-test-v1",
        campaign_template="classic_fantasy",
        depth="quick",
        nodes=(
            CampaignTopicNode(
                topic_id="realm",
                title="Realm",
                category="lore",
                target_count=1,
            ),
            CampaignTopicNode(
                topic_id="actors",
                title="Actors",
                category="actors",
                target_count=2,
            ),
            CampaignTopicNode(
                topic_id="compiler",
                title="Compiler",
                category="compiler",
                target_count=1,
            ),
        ),
    )


def test_default_manifest_is_deterministic_and_matches_topic_cardinality() -> None:
    first = build_entity_manifest(_graph())
    second = build_entity_manifest(_graph())

    assert first == second
    assert first["content_hash"].startswith("sha256:")
    assert first["slot_count"] == 3
    assert first["topics"] == {
        "realm": ["slot:realm:001"],
        "actors": ["slot:actors:001", "slot:actors:002"],
    }
    assert [row["entity_id"] for row in first["slots"]] == [
        "ent:actors:001",
        "ent:actors:002",
        "ent:realm:001",
    ]
    assert all(row["topic_id"] != "compiler" for row in first["slots"])


def test_supplied_manifest_preserves_canonical_ids_and_hints() -> None:
    manifest = build_entity_manifest(
        _graph(),
        {
            "slots": [
                {
                    "slot_id": "slot:realm:capital",
                    "topic_id": "realm",
                    "ordinal": 1,
                    "entity_id": "ent:realm:capital",
                    "domain_id": "realm",
                    "entity_kind": "realm",
                    "name_hint": "The Amber Reach",
                },
                {
                    "slot_id": "slot:actors:warden",
                    "topic_id": "actors",
                    "ordinal": 1,
                    "entity_id": "ent:actor:warden",
                    "domain_id": "actors",
                    "entity_kind": "actor",
                    "name_hint": "Harbormaster Vey",
                },
                {
                    "slot_id": "slot:actors:smuggler",
                    "topic_id": "actors",
                    "ordinal": 2,
                    "entity_id": "ent:actor:smuggler",
                    "domain_id": "actors",
                    "entity_kind": "actor",
                    "name_hint": "Mara Quill",
                },
            ],
            "metadata": {"source": "planner"},
        },
    )

    assert manifest["metadata"] == {"source": "planner"}
    actor_slots = topic_manifest_slots(manifest, "actors")
    assert [row["entity_id"] for row in actor_slots] == [
        "ent:actor:warden",
        "ent:actor:smuggler",
    ]
    assert actor_slots[0]["name_hint"] == "Harbormaster Vey"


def test_duplicate_entity_ids_are_rejected_before_job_creation() -> None:
    supplied = {
        "slots": [
            {
                "topic_id": "realm",
                "ordinal": 1,
                "entity_id": "ent:duplicate",
            },
            {
                "topic_id": "actors",
                "ordinal": 1,
                "entity_id": "ent:duplicate",
            },
            {
                "topic_id": "actors",
                "ordinal": 2,
                "entity_id": "ent:actor:002",
            },
        ]
    }

    with pytest.raises(EntityManifestContractError, match="duplicate_entity_id:ent:duplicate"):
        build_entity_manifest(_graph(), supplied)


def test_missing_or_extra_topic_slots_are_rejected() -> None:
    supplied = {
        "slots": [
            {"topic_id": "realm", "ordinal": 1, "entity_id": "ent:realm:001"},
            {"topic_id": "actors", "ordinal": 1, "entity_id": "ent:actor:001"},
        ]
    }

    with pytest.raises(
        EntityManifestContractError,
        match="manifest_topic_cardinality:actors:expected=2:actual=1",
    ):
        build_entity_manifest(_graph(), supplied)


def test_unknown_manifest_topic_is_rejected() -> None:
    supplied = {
        "slots": [
            {"topic_id": "realm", "ordinal": 1, "entity_id": "ent:realm:001"},
            {"topic_id": "actors", "ordinal": 1, "entity_id": "ent:actor:001"},
            {"topic_id": "actors", "ordinal": 2, "entity_id": "ent:actor:002"},
            {"topic_id": "unplanned", "ordinal": 1, "entity_id": "ent:extra:001"},
        ]
    }

    with pytest.raises(EntityManifestContractError, match="unknown_manifest_topic:unplanned"):
        build_entity_manifest(_graph(), supplied)
