"""End-to-end profile-first World Forge pipeline used before campaign launch."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from .canon_audit import CanonAuditReport, audit_generated_canon
from .canon_compiler import CanonCompilationResult, compile_campaign_bible
from .canon_relationships import compile_cross_domain_relationships
from .contract import CampaignGenesisContract
from .world_forge_anchor_registry import allocate_global_anchor_registry
from .world_forge_causal_evaluation import attach_causal_evaluation
from .world_forge_contract import CampaignTopicGraph, CampaignTopicNode
from .world_forge_generation import (
    GeneratedTopic,
    WorldForgeGenerationResult,
    WorldForgeTopicGenerator,
    generate_campaign_topics,
)
from .world_forge_historical_planning import build_historical_planning_topics
from .world_forge_profile_generation import resolve_or_generate_genre_profile
from .world_forge_profile_graph import (
    build_profile_launch_topic_graph,
    build_profile_topic_graph,
)
from .world_forge_profiles import GenreProfile, genre_profile_from_dict
from .world_forge_quality import apply_world_forge_quality_audit


@dataclass(frozen=True)
class CampaignWorldForgeResult:
    graph: CampaignTopicGraph
    generation: WorldForgeGenerationResult
    relationships: tuple[Mapping[str, Any], ...]
    audit: CanonAuditReport
    compilation: CanonCompilationResult

    @property
    def launch_ready(self) -> bool:
        return (
            self.generation.passed
            and self.audit.passed
            and self.compilation.launch_ready
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "launch_ready": self.launch_ready,
            "graph": self.graph.as_dict(),
            "generation": self.generation.as_dict(),
            "relationships": [dict(row) for row in self.relationships],
            "audit": self.audit.as_dict(),
            "compilation": self.compilation.as_dict(),
        }


def _graph_from_payload(value: Mapping[str, Any]) -> CampaignTopicGraph:
    nodes = tuple(
        CampaignTopicNode(
            topic_id=str(row.get("topic_id") or ""),
            title=str(row.get("title") or ""),
            category=str(row.get("category") or "lore"),
            dependencies=tuple(str(item) for item in row.get("dependencies") or ()),
            generator_role=str(row.get("generator_role") or "world_forge"),
            required_before_launch=bool(row.get("required_before_launch", True)),
            visibility=str(row.get("visibility") or "game_master_canon"),
            target_count=int(row.get("target_count") or 1),
            metadata=dict(row.get("metadata") or {}),
        )
        for row in value.get("nodes") or ()
        if isinstance(row, Mapping)
    )
    return CampaignTopicGraph(
        graph_version=str(value.get("graph_version") or "rpg_profile_topic_graph_v1"),
        campaign_template=str(value.get("campaign_template") or "custom"),
        depth=str(value.get("depth") or "standard"),  # type: ignore[arg-type]
        nodes=nodes,
        metadata=dict(value.get("metadata") or {}),
    )


def _profile_from_graph_or_compiled(
    graph: CampaignTopicGraph,
    compiled_world_forge: Mapping[str, Any],
) -> GenreProfile | None:
    profile_payload = graph.metadata.get("resolved_profile")
    if not isinstance(profile_payload, Mapping):
        resolution = compiled_world_forge.get("genre_profile_resolution")
        if isinstance(resolution, Mapping):
            profile_payload = resolution.get("profile")
    if not isinstance(profile_payload, Mapping):
        return None
    return genre_profile_from_dict(profile_payload).require_valid()


def _deterministic_test_mode() -> bool:
    return str(os.environ.get("RPG_TEST_MODE") or "").strip().casefold() in {
        "deterministic",
        "test",
        "offline",
    }


def _default_generator() -> WorldForgeTopicGenerator:
    if _deterministic_test_mode():
        from .world_forge_default import ReferenceSafeWorldForgeGenerator
        from .world_forge_deterministic import DeterministicWorldForgeGenerator

        return ReferenceSafeWorldForgeGenerator(DeterministicWorldForgeGenerator())

    from app.rpg_world_forge_provider import build_production_world_forge_generator

    return build_production_world_forge_generator()


def run_campaign_world_forge(
    contract: CampaignGenesisContract,
    *,
    campaign_id: str,
    compiled_genesis: Mapping[str, Any] | None = None,
    generator: WorldForgeTopicGenerator | None = None,
    launch_only: bool = False,
    existing_topics: Mapping[str, GeneratedTopic] | None = None,
    canon_revision: int = 1,
) -> CampaignWorldForgeResult:
    """Resolve an ontology, generate structured canon, audit, and compile it."""

    compiled = dict(compiled_genesis or {})
    world_forge = dict(compiled.get("compiled_world_forge") or {})
    graph_payload = world_forge.get("topic_graph")
    profile: GenreProfile | None = None
    if isinstance(graph_payload, Mapping):
        graph = _graph_from_payload(graph_payload)
        profile = _profile_from_graph_or_compiled(graph, world_forge)
    else:
        resolution = resolve_or_generate_genre_profile(
            genre=contract.genre or contract.campaign_template,
            description=" ".join(contract.world_forge.custom_directives),
            campaign_mode=(
                "persistent_living_world"
                if contract.world_options.world_activity == "living_world"
                else "bounded_campaign"
            ),
        )
        profile = resolution.profile
        graph = build_profile_topic_graph(
            profile,
            campaign_template=contract.campaign_template,
            depth=contract.world_forge.depth,
            tone=contract.tone,
            starting_location=contract.world_options.starting_location,
            background_expansion=contract.world_forge.background_expansion,
        )
        profile = _profile_from_graph_or_compiled(graph, world_forge) or profile
    if profile is None:
        raise ValueError("campaign_world_forge_profile_missing")
    if launch_only:
        graph = build_profile_launch_topic_graph(graph, profile)
    graph_issues = graph.validate()
    if graph_issues:
        raise ValueError("invalid campaign topic graph: " + ",".join(graph_issues))

    seed = int(contract.world_options.seed or 0)
    max_parallel_jobs = int(
        world_forge.get("max_parallel_jobs")
        or contract.world_forge.max_parallel_jobs
        or graph.metadata.get("depth_profile", {}).get("max_parallel_jobs")
        or 4
    )
    max_parallel_jobs = max(1, min(max_parallel_jobs, 4))
    profile_payload = profile.as_dict()
    anchor_registry = allocate_global_anchor_registry(
        graph,
        seed=seed,
        world_key=campaign_id,
    )
    planning_topics = {
        "anchor_registry": anchor_registry,
        **build_historical_planning_topics(
            anchor_registry,
            seed=seed,
            world_key=campaign_id,
        ),
    }
    generation = generate_campaign_topics(
        graph,
        generator=generator or _default_generator(),
        seed=seed,
        campaign_context={
            "campaign_id": campaign_id,
            "campaign_template": contract.campaign_template,
            "genre": contract.genre or contract.campaign_template,
            "tone": contract.tone,
            "starting_location": contract.world_options.starting_location,
            "custom_directives": list(contract.world_forge.custom_directives),
            "world_brief": {
                "title": contract.campaign_template.replace("_", " ").title(),
                "description": " ".join(contract.world_forge.custom_directives),
                "genre": contract.genre or contract.campaign_template,
                "tone": contract.tone,
                "campaign_template": contract.campaign_template,
            },
            "resolved_genre_profile": profile_payload,
            "resolved_profile_hash": profile.content_hash,
            "planning_topics": planning_topics,
        },
        max_parallel_jobs=max_parallel_jobs,
        existing_topics=existing_topics,
    )
    relationships = compile_cross_domain_relationships(generation.topics)
    audit = audit_generated_canon(
        generation.topics,
        compiled_relationships=relationships,
    )
    audit = apply_world_forge_quality_audit(generation.topics, audit)
    audit = attach_causal_evaluation(generation.topics, audit)
    compilation = compile_campaign_bible(
        generation,
        compiled_relationships=relationships,
        audit=audit,
        topic_graph=graph.as_dict(),
        campaign_id=campaign_id,
        campaign_template=contract.campaign_template,
        starting_location=contract.world_options.starting_location,
        canon_revision=canon_revision,
    )
    return CampaignWorldForgeResult(
        graph=graph,
        generation=generation,
        relationships=relationships,
        audit=audit,
        compilation=compilation,
    )
