"""Fail-closed validation and trusted-authorship boundary for World Forge jobs."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeTopicGenerator,
    validate_generated_topic_for_publication,
)

from .generation_authorship_runtime import (
    attach_server_llm_authorship,
    build_generation_artifact,
    generation_artifact,
)


def _generator_context(generator: Any) -> dict[str, Any]:
    """Read immutable job identity through spool and provider wrappers."""

    visited: set[int] = set()
    current = generator
    context: dict[str, Any] = {}
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        payload = getattr(current, "payload", None)
        if isinstance(payload, Mapping):
            for key in ("run_id", "job_id", "topic_id", "world_id", "draft_revision"):
                if payload.get(key) not in (None, ""):
                    context.setdefault(key, payload.get(key))
        for key in ("run_id", "job_id", "topic_id", "world_id", "draft_revision"):
            value = getattr(current, key, None)
            if value not in (None, ""):
                context.setdefault(key, value)
        config = getattr(current, "config", None)
        if config is not None:
            context.setdefault("provider", getattr(config, "provider", ""))
            context.setdefault("model", getattr(config, "model", ""))
        current = getattr(current, "generator", None)
    return context


class PublicationValidatedWorldForgeGenerator:
    """Validate the domain value and attach a server-owned field-origin artifact."""

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
        topic = replace(
            validated.topic,
            provenance={
                **dict(validated.topic.provenance),
                "validation_receipt": receipt,
            },
        )
        existing = generation_artifact(topic.as_dict())
        if existing:
            return topic

        context = _generator_context(self.generator)
        provenance = dict(topic.provenance)
        provider = str(provenance.get("provider") or context.get("provider") or "")
        model = str(provenance.get("model") or context.get("model") or "")
        generator_name = str(provenance.get("generator") or "")
        if not generator_name.startswith("structured_world_forge_provider_") or not provider or not model:
            return replace(
                topic,
                provenance={
                    **provenance,
                    "used_llm": False,
                    "generation_status": "needs_review",
                    "generation_review": {
                        "schema_version": "rpg_world_generation_review_v1",
                        "status": "needs_review",
                        "blocking": True,
                        "error_type": "UntrustedGenerationAuthorship",
                        "reason_codes": ["production_generation_artifact_untrusted"],
                        "issues": [
                            {
                                "code": "production_generation_artifact_untrusted",
                                "topic_id": node.topic_id,
                                "entity_id": "",
                                "field_id": "provenance",
                                "message": (
                                    "Production lore requires a configured LLM provider and "
                                    "model. Deterministic and unknown generators are test-only."
                                ),
                            }
                        ],
                        "summary": "Candidate has no publishable LLM authorship artifact.",
                    },
                },
            )

        provider_metadata = {**provenance, "provider": provider, "model": model}
        artifact = build_generation_artifact(
            topic.as_dict(),
            run_id=str(context.get("run_id") or ""),
            job_id=str(context.get("job_id") or ""),
            topic_id=node.topic_id,
            provider=provider_metadata,
            settings={
                "generator_version": provenance.get("generator_version") or "",
                "prompt_version": provenance.get("prompt_version") or "",
            },
            attempt=int(provenance.get("attempt_count") or 1),
        )
        return GeneratedTopic.from_dict(
            attach_server_llm_authorship(topic.as_dict(), artifact)
        )


__all__ = ["PublicationValidatedWorldForgeGenerator"]
