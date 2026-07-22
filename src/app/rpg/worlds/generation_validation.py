"""Fail-closed validation boundary for durable World Forge topic jobs."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeTopicGenerator,
    validate_generated_topic_for_publication,
)


class PublicationValidatedWorldForgeGenerator:
    """Require a canonical domain value and attach its validation receipt."""

    def __init__(self, generator: WorldForgeTopicGenerator) -> None:
        self.generator = generator

    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic:
        generated = self.generator.generate(
            node,
            seed=seed,
            campaign_context=campaign_context,
            dependency_topics=dependency_topics,
        )
        validated = validate_generated_topic_for_publication(
            generated,
            expected_topic_id=node.topic_id,
        )
        receipt = validated.receipt.as_dict()
        return replace(
            validated.topic,
            provenance={
                **dict(validated.topic.provenance),
                "validation_receipt": receipt,
            },
        )


__all__ = ["PublicationValidatedWorldForgeGenerator"]
