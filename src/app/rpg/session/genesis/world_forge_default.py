"""Reference-safe deterministic World Forge generator."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .world_forge_contract import CampaignTopicNode
from .world_forge_deterministic import DeterministicWorldForgeGenerator
from .world_forge_generation import GeneratedTopic


class ReferenceSafeWorldForgeGenerator(DeterministicWorldForgeGenerator):
    """Ensure generated dossier references resolve at every depth profile."""

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
        if node.category == "locations":
            return self._normalize_location_regions(topic, dependency_topics)
        if node.category == "npcs":
            return self._complete_npc_reference_entities(topic, dependency_topics)
        return topic

    @staticmethod
    def _normalize_location_regions(
        topic: GeneratedTopic,
        dependencies: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic:
        region_topic = dependencies.get("regions")
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

    @staticmethod
    def _complete_npc_reference_entities(
        topic: GeneratedTopic,
        dependencies: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic:
        known: dict[str, Mapping[str, Any]] = {}
        for dependency in dependencies.values():
            for entity in dependency.entities:
                entity_id = str(entity.get("id") or "")
                if entity_id:
                    known[entity_id] = entity
        additions: dict[str, dict[str, Any]] = {}
        for npc in topic.entities:
            for faction_id in npc.get("faction_ids") or ():
                faction_id = str(faction_id)
                if faction_id and faction_id not in known:
                    additions[faction_id] = {
                        "id": faction_id,
                        "name": faction_id.split(":", 1)[-1].replace("_", " ").title(),
                        "kind": "faction",
                        "values": ["institutional continuity"],
                        "goals": ["maintain influence over exceptional heroes"],
                        "visibility": "partially_known",
                        "dossier_status": "complete",
                        "generated_for_reference_completeness": True,
                    }
            location_id = str(npc.get("location_id") or "")
            if location_id and location_id not in known:
                additions[location_id] = {
                    "id": location_id,
                    "name": location_id.split(":", 1)[-1].replace("_", " ").title(),
                    "kind": "location",
                    "region_id": next(
                        (
                            str(entity.get("id"))
                            for entity in known.values()
                            if entity.get("kind") == "region"
                        ),
                        "",
                    ),
                    "sensory_profile": "A campaign location compiled to support an opening actor dossier.",
                    "visibility": "partially_known",
                    "dossier_status": "complete",
                    "generated_for_reference_completeness": True,
                }
        if not additions:
            return topic
        facts = [dict(row) for row in topic.facts]
        for entity_id, entity in sorted(additions.items()):
            facts.append(
                {
                    "id": f"fact:{entity_id.replace(':', '_')}:reference",
                    "content": f"{entity['name']} is established campaign canon.",
                    "authority": "generated_proposal",
                    "approved_authority": "objective_canon",
                    "visibility": str(entity.get("visibility") or "game_master_canon"),
                    "entity_refs": [entity_id],
                }
            )
        return replace(
            topic,
            entities=tuple([*topic.entities, *additions.values()]),
            facts=tuple(facts),
            provenance={
                **dict(topic.provenance),
                "reference_completeness_entities": sorted(additions),
            },
        )
