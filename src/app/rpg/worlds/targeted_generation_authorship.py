"""Trusted field-origin helpers for entity and dossier regeneration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeTopicGenerator,
)

from .generation_authorship_runtime import (
    attach_partial_llm_authorship,
    build_generation_artifact,
    generation_artifact,
    generation_artifacts,
    lore_string_leaves,
    require_publishable_authorship,
)
from .generation_validation import PublicationValidatedWorldForgeGenerator


class _TargetedGeneratorContext:
    def __init__(
        self,
        generator: WorldForgeTopicGenerator,
        *,
        run_id: str,
        job_id: str,
        topic_id: str,
    ) -> None:
        self.generator = generator
        self.run_id = run_id
        self.job_id = job_id
        self.topic_id = topic_id

    def generate(self, *args: Any, **kwargs: Any) -> GeneratedTopic:
        return self.generator.generate(*args, **kwargs)


def trusted_targeted_generator(
    generator: WorldForgeTopicGenerator,
    *,
    world_id: str,
    topic_id: str,
    entity_id: str,
    operation: str,
) -> WorldForgeTopicGenerator:
    stamp = datetime.now(timezone.utc).isoformat()
    run_id = f"targeted:{operation}:{world_id}:{topic_id}:{stamp}"
    job_id = f"targeted:{operation}:{entity_id}:{stamp}"
    return PublicationValidatedWorldForgeGenerator(
        _TargetedGeneratorContext(
            generator,
            run_id=run_id,
            job_id=job_id,
            topic_id=topic_id,
        )
    )


def changed_lore_paths(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> tuple[str, ...]:
    prior = {
        str(row["path"]): str(row["content_hash"])
        for row in lore_string_leaves(before)
    }
    return tuple(
        sorted(
            str(row["path"])
            for row in lore_string_leaves(after)
            if prior.get(str(row["path"])) != str(row["content_hash"])
        )
    )


def attach_targeted_regeneration_authorship(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    generated: GeneratedTopic,
    *,
    topic_id: str,
    operation: str,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Attest only changed lore paths to the new provider response."""

    generated_payload = generated.as_dict()
    provider_artifact = generation_artifact(generated_payload)
    if not provider_artifact:
        raise ValueError(
            f"targeted_generation_artifact_required:{topic_id}:{operation}"
        )
    changed = changed_lore_paths(before, after)
    if not changed:
        raise ValueError(f"targeted_generation_changed_lore_required:{topic_id}:{operation}")
    prior_artifacts = generation_artifacts(before)
    provider_artifact_id = str(
        provider_artifact.get("generation_artifact_id") or ""
    )
    parent_ids = tuple(
        dict.fromkeys((*prior_artifacts.keys(), provider_artifact_id))
    )
    provenance = {
        **dict(generated.provenance),
        "raw_response_hash": str(provider_artifact.get("raw_response_hash") or ""),
        "raw_response_hash_kind": str(
            provider_artifact.get("raw_response_hash_kind") or "provider_response"
        ),
        "transformations": ["targeted_regeneration_merge"],
    }
    artifact = build_generation_artifact(
        after,
        run_id=str(provider_artifact.get("generation_run_id") or ""),
        job_id=str(provider_artifact.get("job_id") or ""),
        topic_id=topic_id,
        provider=provenance,
        settings={
            "generator_version": provider_artifact.get("generator_version") or "",
            "prompt_version": provider_artifact.get("prompt_version") or "",
        },
        attempt=int(provider_artifact.get("attempt") or 1),
        authored_paths=changed,
        parent_artifact_ids=parent_ids,
    )
    payload = attach_partial_llm_authorship(
        after,
        artifact,
        llm_paths=changed,
        prior_candidate=before,
    )
    require_publishable_authorship(payload)
    return payload, changed


__all__ = [
    "attach_targeted_regeneration_authorship",
    "changed_lore_paths",
    "trusted_targeted_generator",
]
