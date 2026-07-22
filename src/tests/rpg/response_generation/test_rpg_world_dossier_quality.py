from __future__ import annotations

from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg.session.genesis.world_forge_dossier_quality import (
    content_target,
    dossier_word_count,
    validate_dossier_quality,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic


class _Generator:
    def __init__(self, entity: dict) -> None:
        self.entity = entity

    def generate(self, node, **kwargs):
        return GeneratedTopic(topic_id=node.topic_id, entities=(self.entity,))


def _node(topic_id: str, category: str = "lore") -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id=topic_id,
        title=topic_id.replace("_", " ").title(),
        category=category,
        dependencies=(),
        generator_role="world_forge",
        required_before_launch=True,
        visibility="public",
        target_count=1,
    )


def test_major_legacy_projection_is_enriched_to_multi_paragraph_quality() -> None:
    generator = ReferenceSafeWorldForgeGenerator(
        _Generator(
            {
                "id": "region:ash_wastes",
                "name": "The Ash Wastes",
                "kind": "region",
                "description": "A scarred frontier where old roads disappear beneath radioactive dust.",
            }
        )
    )

    topic = generator.generate(
        _node("regions", "regions"),
        seed=1,
        campaign_context={},
        dependency_topics={},
    )

    dossier = topic.entities[0]["dossier"]
    minimum_words, minimum_sections = content_target("regions")
    assert len(dossier["sections"]) >= minimum_sections
    assert all(len(section["paragraphs"]) >= 1 for section in dossier["sections"])
    assert dossier_word_count(dossier) >= minimum_words
    assert validate_dossier_quality(dossier, topic_id="regions") == ()
    assert topic.provenance["entity_dossier_quality_validated"] is True


def test_explicit_shallow_live_dossier_is_enriched_before_validation() -> None:
    generator = ReferenceSafeWorldForgeGenerator(
        _Generator(
            {
                "id": "faction:thin",
                "name": "Thin Faction",
                "kind": "faction",
                "short_summary": "A short faction summary.",
                "dossier": {
                    "schema_version": "rpg_world_entity_dossier_v1",
                    "sections": [
                        {
                            "id": "overview",
                            "title": "Overview",
                            "paragraphs": ["Only a few words."],
                        }
                    ],
                },
            }
        )
    )

    topic = generator.generate(
        _node("factions", "factions"),
        seed=1,
        campaign_context={},
        dependency_topics={},
    )

    dossier = topic.entities[0]["dossier"]
    assert dossier["quality_enriched"] is True
    assert validate_dossier_quality(dossier, topic_id="factions") == ()
