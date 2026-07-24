"""Reference-safe adapter shared by deterministic and live World Forge generation."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .world_forge_contract import CampaignTopicNode
from .world_forge_deterministic import DeterministicWorldForgeGenerator
from .world_forge_deterministic_completion import complete_deterministic_references
from .world_forge_dossier_quality import (
    dossier_word_count,
    enrich_fallback_dossier,
    validate_dossier_quality,
)
from .world_forge_dossiers import project_entity_dossier, validate_entity_dossier
from .world_forge_domains import (
    normalize_structured_domain,
    validate_world_brief_grounding,
)
from .world_forge_fact_pipeline import compile_structured_entity_facts
from .world_forge_generation import GeneratedTopic, WorldForgeTopicGenerator
from .world_forge_integrity import validate_and_normalize_provider_topic
from .world_forge_semantic_quality import require_topic_semantic_quality


class ReferenceSafeWorldForgeGenerator:
    """Validate live provider references without inventing semantic repairs.

    Deterministic fallback generation keeps isolated synthetic completion for tests
    and offline development. Live provider output is fail-closed: references must
    be exact IDs, explicit aliases, or unique exact names before dossier projection
    or schema completion occurs.
    """

    def __init__(
        self,
        generator: WorldForgeTopicGenerator | None = None,
    ) -> None:
        self.generator = generator or DeterministicWorldForgeGenerator()

    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic:
        topic = self.generator.generate(
            node,
            seed=seed,
            campaign_context=campaign_context,
            dependency_topics=dependency_topics,
        )
        provider_generated = str(
            dict(topic.provenance).get("generator") or ""
        ).startswith("structured_world_forge_provider_")
        if provider_generated:
            aliases = campaign_context.get("reference_aliases")
            topic = validate_and_normalize_provider_topic(
                node,
                topic,
                dependency_topics,
                aliases=dict(aliases) if isinstance(aliases, Mapping) else None,
            )
        topic = normalize_structured_domain(
            node,
            topic,
            dependency_topics,
            allow_synthetic_completion=not provider_generated,
        )
        if not provider_generated:
            topic = complete_deterministic_references(
                node,
                topic,
                dependency_topics,
            )
        topic = compile_structured_entity_facts(
            node,
            topic,
            dependency_topics,
        )
        if provider_generated:
            semantic_report = require_topic_semantic_quality(
                node,
                topic,
                campaign_context,
            )
            topic = replace(
                topic,
                provenance={
                    **dict(topic.provenance),
                    "semantic_quality": semantic_report.as_dict(),
                },
            )
        validate_world_brief_grounding(node, topic, campaign_context)
        return self._normalize_entity_dossiers(node, topic)

    @staticmethod
    def _normalize_entity_dossiers(
        node: CampaignTopicNode,
        topic: GeneratedTopic,
    ) -> GeneratedTopic:
        """Project, enrich, and validate dossiers for every entity-bearing topic."""

        if not topic.entities:
            return topic
        content = topic.as_dict()
        entities: list[dict[str, Any]] = []
        word_counts: dict[str, int] = {}
        for entity in topic.entities:
            row = dict(entity)
            entity_id = str(row.get("id") or row.get("entity_id") or "")
            short_summary, dossier = project_entity_dossier(
                row,
                card_type=node.topic_id,
                content=content,
                entity_id=entity_id,
            )
            quality_issues = validate_dossier_quality(dossier, topic_id=node.topic_id)
            if quality_issues:
                dossier = enrich_fallback_dossier(
                    row,
                    dossier,
                    topic_id=node.topic_id,
                )
                quality_issues = validate_dossier_quality(
                    dossier,
                    topic_id=node.topic_id,
                )
            schema_issues = validate_entity_dossier(dossier)
            issues = (*schema_issues, *quality_issues)
            if issues:
                raise ValueError(
                    f"world_entity_dossier_quality:{node.topic_id}:{entity_id}:"
                    + ",".join(issues)
                )
            row["short_summary"] = short_summary
            row["dossier"] = dossier
            entities.append(row)
            if entity_id:
                word_counts[entity_id] = dossier_word_count(dossier)
        return replace(
            topic,
            entities=tuple(entities),
            provenance={
                **dict(topic.provenance),
                "entity_dossier_schema": "rpg_world_entity_dossier_v1",
                "entity_dossier_quality_validated": True,
                "entity_dossier_word_counts": word_counts,
            },
        )
