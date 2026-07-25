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
from .world_forge_lore_quality import require_provider_lore_quality
from .world_forge_presentation import render_fact_derived_presentations
from .world_forge_profile_deterministic import generate_deterministic_profile_topic
from .world_forge_regeneration import generate_with_targeted_regeneration
from .world_forge_semantic_quality import require_topic_semantic_quality


class ReferenceSafeWorldForgeGenerator:
    """Validate and improve generated topics without inventing semantic repairs."""

    def __init__(
        self,
        generator: WorldForgeTopicGenerator | None = None,
    ) -> None:
        self.generator = generator or DeterministicWorldForgeGenerator()

    @staticmethod
    def _provider_generated(topic: GeneratedTopic) -> bool:
        return str(dict(topic.provenance).get("generator") or "").startswith(
            "structured_world_forge_provider_"
        )

    @staticmethod
    def _max_regeneration_attempts(campaign_context: Mapping[str, Any]) -> int:
        try:
            return max(
                1,
                min(
                    int(campaign_context.get("targeted_regeneration_max_attempts") or 3),
                    5,
                ),
            )
        except (TypeError, ValueError):
            return 3

    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic:
        def process(topic: GeneratedTopic) -> GeneratedTopic:
            return self._process_topic(
                node,
                topic,
                campaign_context=campaign_context,
                dependency_topics=dependency_topics,
            )

        # The legacy deterministic generator dispatches several mature topic IDs
        # through fixed fantasy-era schemas. Profile-defined topics may intentionally
        # reuse those IDs with different entity kinds and reference domains. Enter
        # through the profile generator directly so quests can reference
        # actor/place/group rather than being rejected for lacking npc/location/faction.
        if (
            node.metadata.get("field_definitions")
            and isinstance(self.generator, DeterministicWorldForgeGenerator)
        ):
            return process(
                generate_deterministic_profile_topic(
                    node,
                    campaign_context=campaign_context,
                    dependency_topics=dependency_topics,
                )
            )

        return generate_with_targeted_regeneration(
            self.generator,
            node,
            seed=seed,
            campaign_context=campaign_context,
            dependency_topics=dependency_topics,
            process=process,
            max_attempts=self._max_regeneration_attempts(campaign_context),
        )

    def _process_topic(
        self,
        node: CampaignTopicNode,
        topic: GeneratedTopic,
        *,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic:
        provider_generated = self._provider_generated(topic)
        profile_defined = bool(node.metadata.get("field_definitions"))
        if provider_generated and not profile_defined:
            aliases = campaign_context.get("reference_aliases")
            topic = validate_and_normalize_provider_topic(
                node,
                topic,
                dependency_topics,
                aliases=dict(aliases) if isinstance(aliases, Mapping) else None,
            )

        # Profile field definitions are the authoritative ontology. A profile may
        # deliberately reuse a mature topic ID such as quests or opening_scenarios
        # while changing its entity kinds and reference domains. Running those
        # records through the legacy fixed-domain normalizer or integrity map first
        # would incorrectly require npc/location/faction IDs and reject
        # actor/place/group canon. Profile-defined provider output remains fail-closed
        # below through compile_structured_entity_facts, which validates IDs, kinds,
        # required fields, value types, allowed target domains, and exact references.
        if not profile_defined:
            topic = normalize_structured_domain(
                node,
                topic,
                dependency_topics,
                allow_synthetic_completion=not provider_generated,
            )

        if not provider_generated and profile_defined:
            topic = generate_deterministic_profile_topic(
                node,
                campaign_context=campaign_context,
                dependency_topics=dependency_topics,
            )
        elif not provider_generated:
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
        if profile_defined:
            rendered = render_fact_derived_presentations(node, topic)
            if provider_generated:
                rendered = require_provider_lore_quality(
                    node,
                    rendered,
                    campaign_context,
                )
            return rendered
        return self._normalize_entity_dossiers(node, topic)

    @staticmethod
    def _normalize_entity_dossiers(
        node: CampaignTopicNode,
        topic: GeneratedTopic,
    ) -> GeneratedTopic:
        """Project and validate legacy fixed-domain dossiers."""

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
