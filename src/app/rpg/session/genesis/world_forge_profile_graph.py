"""Compile full and launch CampaignTopicGraph objects from validated profiles."""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .world_forge_authorship_policy import field_policy_row, topic_authorship_policy
from .world_forge_causal_profile import augment_profile_with_causal_traceability
from .world_forge_contract import CampaignTopicGraph, CampaignTopicNode
from .world_forge_lore_quality import lore_quality_contract
from .world_forge_profiles import DomainDefinition, GenreProfile

_PIPELINE_CATEGORIES = {"compiler", "audit", "index", "bootstrap"}


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _field_metadata(domain: DomainDefinition) -> dict[str, Any]:
    required_fields = [field.field_id for field in domain.fields if field.required]
    reference_fields = {
        field.field_id: {
            "value_type": field.value_type,
            "allowed_target_domains": list(field.allowed_target_domains),
        }
        for field in domain.fields
        if field.value_type in {"entity_ref", "entity_ref_list"}
    }
    guidance = dict(domain.generation_guidance)
    presentation = _record(guidance.get("presentation"))
    return {
        "entity_kind": domain.entity_kind,
        "required_entity_fields": required_fields,
        "field_definitions": [field_policy_row(field) for field in domain.fields],
        "authorship_policy": topic_authorship_policy(domain.fields),
        "reference_fields": reference_fields,
        "semantic_roles": list(domain.semantic_roles),
        "generation_guidance": guidance,
        "presentation": presentation,
        "schema_version": f"rpg_profile_domain_{domain.domain_id}_v1",
    }


def _effective_dependencies(domain: DomainDefinition) -> tuple[str, ...]:
    """Make every cross-domain typed reference available to the generator.

    Profile fields are validated against the dependency topics passed into a single
    generation job. Authors should not have to duplicate every reference target in
    the handwritten dependency list, and self-references such as parent_place_id do
    not require a separate graph edge.
    """

    reference_domains = (
        target
        for field in domain.fields
        if field.value_type in {"entity_ref", "entity_ref_list"}
        for target in field.allowed_target_domains
        if target != domain.domain_id
    )
    return tuple(dict.fromkeys((*domain.dependencies, *reference_domains)))


def _domain_node(domain: DomainDefinition, *, depth: str) -> CampaignTopicNode:
    metadata = _field_metadata(domain)
    presentation = _record(metadata.get("presentation"))
    page_kind = str(presentation.get("page_kind") or "document")
    category = domain.category
    if category == "domain":
        category = domain.domain_id if page_kind == "collection" else "lore"
    probe = CampaignTopicNode(
        topic_id=domain.domain_id,
        title=domain.title,
        category=category,
        dependencies=_effective_dependencies(domain),
        generator_role=domain.generator_role,
        required_before_launch=domain.required_before_launch,
        visibility=domain.visibility_default,
        target_count=max(1, domain.target_range.target(depth)),
        metadata=metadata,
    )
    configured_lore_quality = _record(
        _record(domain.generation_guidance).get("lore_quality")
    )
    metadata["lore_quality"] = configured_lore_quality or lore_quality_contract(probe)
    return CampaignTopicNode(
        topic_id=probe.topic_id,
        title=probe.title,
        category=probe.category,
        dependencies=probe.dependencies,
        generator_role=probe.generator_role,
        required_before_launch=probe.required_before_launch,
        visibility=probe.visibility,
        target_count=probe.target_count,
        metadata=metadata,
    )


def _pipeline_nodes(domain_ids: tuple[str, ...]) -> tuple[CampaignTopicNode, ...]:
    return (
        CampaignTopicNode(
            topic_id="relationships",
            title="Cross-domain Relationships",
            category="compiler",
            dependencies=domain_ids,
            generator_role="relationship_compiler",
        ),
        CampaignTopicNode(
            topic_id="consistency_audit",
            title="Canon Consistency Audit",
            category="audit",
            dependencies=("relationships",),
            generator_role="canon_critic",
        ),
        CampaignTopicNode(
            topic_id="canon_compile",
            title="Canon Compilation",
            category="compiler",
            dependencies=("consistency_audit",),
            generator_role="canon_compiler",
        ),
        CampaignTopicNode(
            topic_id="retrieval_index",
            title="Lore Retrieval Index",
            category="index",
            dependencies=("canon_compile",),
            generator_role="retrieval_index_compiler",
        ),
        CampaignTopicNode(
            topic_id="opening_materialization",
            title="Opening Scene Materialization",
            category="bootstrap",
            dependencies=("canon_compile", "retrieval_index"),
            generator_role="campaign_materializer",
        ),
    )


def build_profile_topic_graph(
    profile: GenreProfile,
    *,
    campaign_template: str,
    depth: str = "standard",
    tone: str = "",
    starting_location: str = "",
    background_expansion: bool = False,
    runtime_capabilities: dict[str, bool] | None = None,
) -> CampaignTopicGraph:
    """Build a deterministic graph from the exact validated profile revision."""

    profile = augment_profile_with_causal_traceability(profile)
    domain_nodes = tuple(_domain_node(domain, depth=depth) for domain in profile.domains)
    domain_ids = tuple(domain.domain_id for domain in profile.domains)
    graph = CampaignTopicGraph(
        graph_version="rpg_profile_topic_graph_v2",
        campaign_template=str(campaign_template or profile.profile_id),
        depth=str(depth or "standard"),  # type: ignore[arg-type]
        nodes=(*domain_nodes, *_pipeline_nodes(domain_ids)),
        metadata={
            "genre_profile_id": profile.profile_id,
            "genre_profile_version": profile.version,
            "resolved_profile_hash": profile.content_hash,
            "resolved_profile": profile.as_dict(),
            "genre_tags": list(profile.genre_tags),
            "tone": str(tone or ""),
            "starting_location": str(starting_location or ""),
            "background_expansion": bool(background_expansion),
            "runtime_capabilities": {
                **profile.runtime_capability_defaults.as_dict(),
                **dict(runtime_capabilities or {}),
            },
            "launch_requirements": profile.launch_requirements.as_dict(),
        },
    )
    issues = graph.validate()
    if issues:
        raise ValueError("invalid_profile_campaign_topic_graph:" + ",".join(issues))
    return graph


def _dependency_closure(
    graph: CampaignTopicGraph,
    selected_ids: Iterable[str],
) -> set[str]:
    node_map = graph.node_map()
    selected = {str(topic_id) for topic_id in selected_ids}
    pending = list(selected)
    while pending:
        topic_id = pending.pop()
        node = node_map.get(topic_id)
        if node is None:
            continue
        for dependency in node.dependencies:
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)
    return selected


def build_profile_launch_topic_graph(
    graph: CampaignTopicGraph,
    profile: GenreProfile,
) -> CampaignTopicGraph:
    """Project the first-turn graph from profile launch requirements."""

    profile = augment_profile_with_causal_traceability(profile)
    selected = set(profile.launch_requirements.required_domain_ids)
    selected.update(
        domain.domain_id
        for domain in profile.domains
        if domain.required_before_launch
        or set(domain.semantic_roles)
        & set(profile.launch_requirements.required_semantic_roles)
    )
    selected = _dependency_closure(graph, selected)
    selected.update(_PIPELINE_CATEGORIES)
    pipeline_ids = {
        node.topic_id
        for node in graph.nodes
        if node.category in _PIPELINE_CATEGORIES
    }
    selected.update(pipeline_ids)

    nodes: list[CampaignTopicNode] = []
    for node in graph.topological_order():
        if node.topic_id not in selected:
            continue
        dependencies = tuple(
            dependency for dependency in node.dependencies if dependency in selected
        )
        if node.topic_id == "relationships":
            dependencies = tuple(
                domain.domain_id
                for domain in profile.domains
                if domain.domain_id in selected
            )
        nodes.append(
            CampaignTopicNode(
                topic_id=node.topic_id,
                title=node.title,
                category=node.category,
                dependencies=dependencies,
                generator_role=node.generator_role,
                required_before_launch=True,
                visibility=node.visibility,
                target_count=node.target_count,
                metadata=dict(node.metadata),
            )
        )

    projected = CampaignTopicGraph(
        graph_version=graph.graph_version,
        campaign_template=graph.campaign_template,
        depth=graph.depth,
        nodes=tuple(nodes),
        metadata={
            **dict(graph.metadata),
            "generation_tier": "launch_canon",
            "deferred_topic_ids": [
                node.topic_id
                for node in graph.topological_order()
                if node.topic_id not in selected
                and node.category not in _PIPELINE_CATEGORIES
            ],
        },
    )
    issues = projected.validate()
    if issues:
        raise ValueError("invalid_profile_launch_topic_graph:" + ",".join(issues))
    missing = set(profile.launch_requirements.required_domain_ids) - set(
        projected.node_map()
    )
    if missing:
        raise ValueError("profile_launch_topics_missing:" + ",".join(sorted(missing)))
    return projected
