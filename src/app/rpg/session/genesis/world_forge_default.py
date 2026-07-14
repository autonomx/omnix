"""Reference-safe deterministic World Forge generator."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .world_forge_contract import CampaignTopicNode
from .world_forge_deterministic import DeterministicWorldForgeGenerator
from .world_forge_generation import GeneratedTopic


class ReferenceSafeWorldForgeGenerator(DeterministicWorldForgeGenerator):
    """Normalize fallback location parents against generated region canon."""

    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic:
        topic = super().generate(
            node,
            seed=seed,
            campaign_context=campaign_context,
            dependency_topics=dependency_topics,
        )
        if node.category != "locations":
            return topic
        region_topic = dependency_topics.get("regions")
        valid_regions = {
            str(entity.get("id") or "")
            for entity in (region_topic.entities if region_topic is not None else ())
            if str(entity.get("id") or "")
        }
        if not valid_regions:
            return topic
        preferred = "region:aertos" if "region:aertos" in valid_regions else sorted(valid_regions)[0]
        replacements: dict[str, str] = {}
        entities: list[dict[str, Any]] = []
        for entity in topic.entities:
            row = dict(entity)
            parent = str(row.get("region_id") or "")
            if parent and parent not in valid_regions:
                replacements[parent] = preferred
                row["region_id"] = preferred
                row["reference_normalized"] = True
            entities.append(row)

        def normalized_refs(value: Any) -> list[str]:
            return [replacements.get(str(ref), str(ref)) for ref in value or ()]

        facts = []
        for fact in topic.facts:
            row = dict(fact)
            row["entity_refs"] = normalized_refs(row.get("entity_refs"))
            facts.append(row)
        documents = []
        for document in topic.documents:
            row = dict(document)
            row["entities"] = normalized_refs(row.get("entities"))
            documents.append(row)
        return replace(
            topic,
            documents=tuple(documents),
            entities=tuple(entities),
            facts=tuple(facts),
            provenance={
                **dict(topic.provenance),
                "reference_normalizer": "generated_region_parent_v1",
                "reference_replacements": replacements,
            },
        )
