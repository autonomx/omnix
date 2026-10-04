from __future__ import annotations

from typing import Mapping

from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.worlds.generation_validation import PublicationValidatedWorldForgeGenerator


class _Provider:
    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, object],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic:
        del seed, campaign_context, dependency_topics
        return GeneratedTopic(
            topic_id=node.topic_id,
            entities=(
                {"id": "provider:one", "name": "One", "ally_id": "provider:two"},
                {"id": "provider:two", "name": "Two"},
            ),
            relationships=(
                {
                    "id": "rel:allies",
                    "source_id": "provider:one",
                    "target_id": "provider:two",
                },
            ),
            provenance={"generator": "deterministic_world_forge_v1"},
        )


def test_publication_validation_boundary_injects_manifest_ids(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RPG_TEST_MODE", "deterministic")
    node = CampaignTopicNode(
        topic_id="actors",
        title="Actors",
        category="actors",
        target_count=2,
        metadata={
            "entity_manifest_hash": "sha256:manifest",
            "entity_manifest_slots": [
                {
                    "slot_id": "slot:actors:001",
                    "topic_id": "actors",
                    "ordinal": 1,
                    "entity_id": "ent:actor:one",
                },
                {
                    "slot_id": "slot:actors:002",
                    "topic_id": "actors",
                    "ordinal": 2,
                    "entity_id": "ent:actor:two",
                },
            ],
        },
    )

    generated = PublicationValidatedWorldForgeGenerator(_Provider()).generate(
        node,
        seed=1,
        campaign_context={},
        dependency_topics={},
    )

    assert [row["id"] for row in generated.entities] == [
        "ent:actor:one",
        "ent:actor:two",
    ]
    assert generated.entities[0]["ally_id"] == "ent:actor:two"
    assert generated.relationships[0]["source_id"] == "ent:actor:one"
    assert generated.relationships[0]["target_id"] == "ent:actor:two"
    binding = generated.provenance["entity_manifest_binding"]
    assert binding["manifest_hash"] == "sha256:manifest"
    assert binding["slot_count"] == 2
    assert generated.provenance["generation_status"] == "accepted"
