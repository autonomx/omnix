"""World Forge generator wrapper that creates server-owned authorship artifacts."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeTopicGenerator,
)

from .generation_authorship_runtime import (
    attach_server_llm_authorship,
    build_generation_artifact,
)
from .generation_test_mode import deterministic_world_forge_test_mode


class TrustedAuthorshipWorldForgeGenerator:
    """Attach exact field origins before a candidate reaches durable storage."""

    def __init__(
        self,
        generator: WorldForgeTopicGenerator,
        *,
        run_id: str,
        job_id: str,
        topic_id: str,
        settings: Mapping[str, Any],
        fingerprint: str = "",
        directive_hash: str = "",
        entity_manifest_hash: str = "",
    ) -> None:
        self.generator = generator
        self.run_id = run_id
        self.job_id = job_id
        self.topic_id = topic_id
        self.settings = dict(settings)
        self.fingerprint = fingerprint
        self.directive_hash = directive_hash
        self.entity_manifest_hash = entity_manifest_hash

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
        provenance = {
            **dict(topic.provenance),
            "generation_fingerprint": self.fingerprint,
            "directive_hash": self.directive_hash,
            "entity_manifest_hash": self.entity_manifest_hash,
            "job_id": self.job_id,
            "run_id": self.run_id,
        }
        topic = replace(topic, provenance=provenance)
        provider = str(provenance.get("provider") or "")
        model = str(provenance.get("model") or "")
        generator_name = str(provenance.get("generator") or "")
        provider_generated = generator_name.startswith("structured_world_forge_provider_")
        if not provider_generated or not provider or not model:
            if deterministic_world_forge_test_mode() and (
                generator_name.startswith("deterministic_")
                or bool(provenance.get("deterministic_fixture_only"))
                or bool(provenance.get("deterministic_fixture_fact_presentation"))
            ):
                return replace(
                    topic,
                    provenance={
                        **provenance,
                        "used_llm": False,
                        "deterministic_fixture_only": True,
                        "generation_status": "accepted",
                        "test_authorship_exemption": {
                            "schema_version": "rpg_deterministic_fixture_exemption_v1",
                            "reason": "explicit_rpg_test_mode",
                            "publishable_outside_test_mode": False,
                        },
                    },
                )
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
                                    "Production lore requires an approved provider and model; "
                                    "deterministic or unknown generation cannot be published."
                                ),
                            }
                        ],
                        "summary": "Candidate has no publishable LLM authorship artifact.",
                    },
                },
            )
        payload = topic.as_dict()
        artifact = build_generation_artifact(
            payload,
            run_id=self.run_id,
            job_id=self.job_id,
            topic_id=self.topic_id,
            provider=provenance,
            settings=self.settings,
            attempt=int(provenance.get("attempt_count") or 1),
        )
        authored = attach_server_llm_authorship(payload, artifact)
        return GeneratedTopic.from_dict(authored)


__all__ = ["TrustedAuthorshipWorldForgeGenerator"]
