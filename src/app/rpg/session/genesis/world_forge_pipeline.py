"""End-to-end in-memory World Forge pipeline used before campaign launch."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .canon_audit import CanonAuditReport, audit_generated_canon
from .canon_compiler import CanonCompilationResult, compile_campaign_bible
from .canon_relationships import compile_cross_domain_relationships
from .contract import CampaignGenesisContract
from .world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
    build_campaign_topic_graph,
)
from .world_forge_generation import (
    WorldForgeGenerationResult,
    WorldForgeTopicGenerator,
    generate_campaign_topics,
)


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
        graph_version=str(value.get("graph_version") or "rpg_campaign_topic_graph_v1"),
        campaign_template=str(value.get("campaign_template") or "classic_fantasy"),
        depth=str(value.get("depth") or "standard"),  # type: ignore[arg-type]
        nodes=nodes,
        metadata=dict(value.get("metadata") or {}),
    )


def _default_generator() -> WorldForgeTopicGenerator:
    from .world_forge_default import ReferenceSafeWorldForgeGenerator

    return ReferenceSafeWorldForgeGenerator()


def run_campaign_world_forge(
    contract: CampaignGenesisContract,
    *,
    campaign_id: str,
    compiled_genesis: Mapping[str, Any] | None = None,
    generator: WorldForgeTopicGenerator | None = None,
) -> CampaignWorldForgeResult:
    """Generate, cross-link, audit, and compile one campaign before its first turn."""

    compiled = dict(compiled_genesis or {})
    world_forge = dict(compiled.get("compiled_world_forge") or {})
    graph_payload = world_forge.get("topic_graph")
    if isinstance(graph_payload, Mapping):
        graph = _graph_from_payload(graph_payload)
    else:
        graph = build_campaign_topic_graph(
            campaign_template=contract.campaign_template,
            genre=contract.genre,
            tone=contract.tone,
            depth=contract.world_forge.depth,
            starting_location=contract.world_options.starting_location,
            background_expansion=contract.world_forge.background_expansion,
        )
    graph_issues = graph.validate()
    if graph_issues:
        raise ValueError("invalid campaign topic graph: " + ",".join(graph_issues))
    seed = int(contract.world_options.seed or 0)
    max_parallel_jobs = int(
        world_forge.get("max_parallel_jobs")
        or contract.world_forge.max_parallel_jobs
        or graph.metadata.get("depth_profile", {}).get("max_parallel_jobs")
        or 6
    )
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
        },
        max_parallel_jobs=max_parallel_jobs,
    )
    relationships = compile_cross_domain_relationships(generation.topics)
    audit = audit_generated_canon(
        generation.topics,
        compiled_relationships=relationships,
    )
    compilation = compile_campaign_bible(
        generation,
        compiled_relationships=relationships,
        audit=audit,
        topic_graph=graph.as_dict(),
        campaign_id=campaign_id,
        campaign_template=contract.campaign_template,
        starting_location=contract.world_options.starting_location,
        canon_revision=1,
    )
    return CampaignWorldForgeResult(
        graph=graph,
        generation=generation,
        relationships=relationships,
        audit=audit,
        compilation=compilation,
    )
