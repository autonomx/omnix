"""Compile full and launch CampaignTopicGraph objects from validated profiles."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable, Mapping

from .world_forge_authorship_policy import field_policy_row, topic_authorship_policy
from .world_forge_causal_generation import causal_generation_contract
from .world_forge_causal_profile import augment_profile_with_causal_traceability
from .world_forge_contract import CampaignTopicGraph, CampaignTopicNode
from .world_forge_lore_quality import lore_quality_contract
from .world_forge_planning import planning_contract_metadata
from .world_forge_profiles import DomainDefinition, FieldDefinition, GenreProfile
from .world_forge_spatial_routes import minimum_route_count

_PIPELINE_CATEGORIES = {"compiler", "audit", "index", "bootstrap"}
_MISSION_DOMAIN_IDS = {
    "quests",
    "encounter_seeds",
    "opening_threads",
    "opening_scenarios",
}
_ACTOR_DOMAIN_IDS = {"actors"}
_NETWORK_DOMAIN_IDS = {"networks"}
_SPATIAL_DOMAIN_IDS = {"places"}
_ECONOMIC_SCALE_DOMAIN_IDS = {"places", "economy_law"}
_RESOURCE_DOMAIN_IDS = {
    "groups",
    "technology_augmentations",
    "economy_law",
}
_RESOURCE_PROVIDER_TARGETS = {
    "groups": ("places",),
    "technology_augmentations": ("groups",),
    "economy_law": ("groups",),
}
_RESOURCE_CONSUMER_TARGETS = {
    "groups": ("places",),
    "technology_augmentations": ("groups",),
    "economy_law": ("places",),
}
_NETWORK_CAPABILITY = "digital_spaces"
_MISSION_FIELDS = (
    FieldDefinition(
        field_id="mission_signature",
        value_type="structured_object",
        required=True,
        semantic_role="mission_signature",
        description=(
            "Structured mission shape with activity, target, location, principal_actor, "
            "antagonist, pressure, resolution_modes, and consequence_type."
        ),
    ),
    FieldDefinition(
        field_id="campaign_arc_id",
        value_type="string",
        required=False,
        semantic_role="campaign_arc",
        description="Stable arc ID only when this mission is an intentional sequence member.",
    ),
    FieldDefinition(
        field_id="arc_role",
        value_type="string",
        required=False,
        semantic_role="campaign_arc",
        description="Distinct role within an intentional arc, such as setup or reversal.",
    ),
    FieldDefinition(
        field_id="arc_sequence",
        value_type="integer",
        required=False,
        semantic_role="campaign_arc",
        description="Positive unique order within an intentional campaign arc.",
    ),
)
_ACTOR_FIELDS = (
    FieldDefinition(
        field_id="incentive_signature",
        value_type="structured_object",
        required=True,
        semantic_role="actor_incentive_signature",
        description=(
            "Structured actor incentive with primary_motive, scarce_need, dependency_type, "
            "risk_tolerance, preferred_method, red_line, alliance_preference, and "
            "conflict_preference. Use concise categorical values, not prose."
        ),
    ),
)
_NETWORK_FIELDS = (
    FieldDefinition(
        field_id="controller_group_ids",
        value_type="entity_ref_list",
        required=True,
        allowed_target_domains=("groups",),
        semantic_role="network_controller",
        description="Canonical groups that operate, govern, or can disable this network.",
    ),
    FieldDefinition(
        field_id="covered_place_ids",
        value_type="entity_ref_list",
        required=True,
        allowed_target_domains=("places",),
        semantic_role="network_coverage",
        description=(
            "Canonical places reached by this network; never claim universal "
            "coverage in prose."
        ),
    ),
    FieldDefinition(
        field_id="network_constraint_signature",
        value_type="structured_object",
        required=True,
        semantic_role="network_constraint_signature",
        description=(
            "Structured bounded network model with coverage_scope, access_model, "
            "latency_class, monitoring_mode, blind_spot, traceability_limit, "
            "failure_mode, and jurisdiction_model. Use concise categorical values, "
            "not prose."
        ),
    ),
)
_SPATIAL_FIELDS = (
    FieldDefinition(
        field_id="connected_place_ids",
        value_type="entity_ref_list",
        required=True,
        allowed_target_domains=("places",),
        semantic_role="travel_route",
        description=(
            "Canonical places directly reachable from this place. Do not include "
            "the current place or invent unregistered endpoints."
        ),
    ),
    FieldDefinition(
        field_id="travel_route_signature",
        value_type="structured_object",
        required=True,
        semantic_role="travel_route_signature",
        description=(
            "Structured route constraints with travel_time_band, access_mode, "
            "route_blocker, failure_condition, capacity_class, and "
            "information_delay. Portals are allowed only as explicit access modes "
            "with non-zero time, blockers, and failure conditions."
        ),
    ),
)
_ECONOMIC_SCALE_FIELDS = (
    FieldDefinition(
        field_id="economic_scale_signature",
        value_type="structured_object",
        required=True,
        semantic_role="economic_scale_signature",
        description=(
            "Structured representative scale with scale_scope, "
            "served_population_band, workforce_band, service_reach_band, "
            "throughput_band, price_basis, scarcity_level, reserve_horizon, and "
            "demand_pressure. Use bounded categorical bands, not invented precise "
            "statistics or universal claims."
        ),
    ),
)


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _network_contract_enabled(
    domain: DomainDefinition,
    capability_flags: Mapping[str, bool],
) -> bool:
    return bool(capability_flags.get(_NETWORK_CAPABILITY)) and (
        domain.domain_id in _NETWORK_DOMAIN_IDS
    )


def _spatial_contract_enabled(domain: DomainDefinition) -> bool:
    return domain.domain_id in _SPATIAL_DOMAIN_IDS and domain.target_range.epic[1] > 1


def _economic_scale_contract_enabled(domain: DomainDefinition) -> bool:
    return domain.domain_id in _ECONOMIC_SCALE_DOMAIN_IDS


def _resource_contract_enabled(domain: DomainDefinition) -> bool:
    return domain.domain_id in _RESOURCE_DOMAIN_IDS


def _resource_fields(domain: DomainDefinition) -> tuple[FieldDefinition, ...]:
    if not _resource_contract_enabled(domain):
        return ()
    return (
        FieldDefinition(
            field_id="resource_provider_ids",
            value_type="entity_ref_list",
            required=True,
            allowed_target_domains=_RESOURCE_PROVIDER_TARGETS[domain.domain_id],
            semantic_role="resource_provider",
            description=(
                "Canonical places or groups that supply a required input to this "
                "institution, technology, or system."
            ),
        ),
        FieldDefinition(
            field_id="resource_consumer_ids",
            value_type="entity_ref_list",
            required=True,
            allowed_target_domains=_RESOURCE_CONSUMER_TARGETS[domain.domain_id],
            semantic_role="resource_consumer",
            description=(
                "Canonical places or groups that depend on this entity's output; "
                "provider and consumer sets must not be identical."
            ),
        ),
        FieldDefinition(
            field_id="resource_dependency_signature",
            value_type="structured_object",
            required=True,
            semantic_role="resource_dependency_signature",
            description=(
                "Structured resource model with resource_class, supply_mode, "
                "dependency_strength, substitute_class, bottleneck_type, "
                "depletion_horizon, failure_consequence, and recovery_mode. Use "
                "concise categorical values, not prose."
            ),
        ),
    )


def _domain_fields(
    domain: DomainDefinition,
    capability_flags: Mapping[str, bool],
) -> tuple[FieldDefinition, ...]:
    network_enabled = _network_contract_enabled(domain, capability_flags)
    economic_scale_enabled = _economic_scale_contract_enabled(domain)
    fields = [
        replace(field, required=True)
        if (
            network_enabled and field.field_id == "controller_group_ids"
        )
        or (
            economic_scale_enabled
            and domain.domain_id == "economy_law"
            and field.field_id == "affected_place_ids"
        )
        else field
        for field in domain.fields
    ]
    existing = {field.field_id for field in fields}
    additions: tuple[FieldDefinition, ...] = ()
    if domain.domain_id in _MISSION_DOMAIN_IDS:
        additions = (*additions, *_MISSION_FIELDS)
    if domain.domain_id in _ACTOR_DOMAIN_IDS:
        additions = (*additions, *_ACTOR_FIELDS)
    if network_enabled:
        additions = (*additions, *_NETWORK_FIELDS)
    if _spatial_contract_enabled(domain):
        additions = (*additions, *_SPATIAL_FIELDS)
    if economic_scale_enabled:
        additions = (*additions, *_ECONOMIC_SCALE_FIELDS)
    if _resource_contract_enabled(domain):
        additions = (*additions, *_resource_fields(domain))
    fields.extend(field for field in additions if field.field_id not in existing)
    return tuple(fields)


def _field_metadata(
    domain: DomainDefinition,
    capability_flags: Mapping[str, bool],
    *,
    depth: str,
) -> dict[str, Any]:
    fields = _domain_fields(domain, capability_flags)
    required_fields = [field.field_id for field in fields if field.required]
    reference_fields = {
        field.field_id: {
            "value_type": field.value_type,
            "allowed_target_domains": list(field.allowed_target_domains),
        }
        for field in fields
        if field.value_type in {"entity_ref", "entity_ref_list"}
    }
    guidance = dict(domain.generation_guidance)
    presentation = _record(guidance.get("presentation"))
    network_enabled = _network_contract_enabled(domain, capability_flags)
    spatial_enabled = _spatial_contract_enabled(domain)
    economic_scale_enabled = _economic_scale_contract_enabled(domain)
    resource_enabled = _resource_contract_enabled(domain)
    upgraded = (
        domain.domain_id in _MISSION_DOMAIN_IDS
        or domain.domain_id in _ACTOR_DOMAIN_IDS
        or network_enabled
        or spatial_enabled
        or economic_scale_enabled
        or resource_enabled
    )
    metadata = {
        "entity_kind": domain.entity_kind,
        "required_entity_fields": required_fields,
        "field_definitions": [field_policy_row(field) for field in fields],
        "authorship_policy": topic_authorship_policy(fields),
        "reference_fields": reference_fields,
        "semantic_roles": list(domain.semantic_roles),
        "generation_guidance": guidance,
        "presentation": presentation,
        "schema_version": (
            f"rpg_profile_domain_{domain.domain_id}_v2"
            if upgraded
            else f"rpg_profile_domain_{domain.domain_id}_v1"
        ),
    }
    if domain.domain_id in _MISSION_DOMAIN_IDS:
        metadata["mission_signature_contract"] = {
            "schema_version": "rpg_world_mission_signature_contract_v1",
            "required": True,
            "signature_field": "mission_signature",
            "arc_fields": ["campaign_arc_id", "arc_role", "arc_sequence"],
            "signature_components": [
                "activity",
                "target",
                "location",
                "principal_actor",
                "antagonist",
                "pressure",
                "resolution_modes",
                "consequence_type",
            ],
        }
    if domain.domain_id in _ACTOR_DOMAIN_IDS:
        metadata["actor_incentive_contract"] = {
            "schema_version": "rpg_world_actor_incentive_contract_v1",
            "required": True,
            "signature_field": "incentive_signature",
            "signature_components": [
                "primary_motive",
                "scarce_need",
                "dependency_type",
                "risk_tolerance",
                "preferred_method",
                "red_line",
                "alliance_preference",
                "conflict_preference",
            ],
        }
    if network_enabled:
        metadata["network_constraint_contract"] = {
            "schema_version": "rpg_world_network_constraint_contract_v1",
            "required": True,
            "capability": _NETWORK_CAPABILITY,
            "controller_field": "controller_group_ids",
            "coverage_field": "covered_place_ids",
            "signature_field": "network_constraint_signature",
            "signature_components": [
                "coverage_scope",
                "access_model",
                "latency_class",
                "monitoring_mode",
                "blind_spot",
                "traceability_limit",
                "failure_mode",
                "jurisdiction_model",
            ],
        }
    if spatial_enabled:
        place_count = max(1, domain.target_range.target(depth))
        metadata["spatial_route_contract"] = {
            "schema_version": "rpg_world_spatial_route_contract_v1",
            "required": True,
            "connection_field": "connected_place_ids",
            "signature_field": "travel_route_signature",
            "signature_components": [
                "travel_time_band",
                "access_mode",
                "route_blocker",
                "failure_condition",
                "capacity_class",
                "information_delay",
            ],
            "place_count": place_count,
            "minimum_route_count": minimum_route_count(place_count, depth),
            "depth": str(depth or "standard"),
        }
    if economic_scale_enabled:
        metadata["economic_scale_contract"] = {
            "schema_version": "rpg_world_economic_scale_contract_v1",
            "required": True,
            "signature_field": "economic_scale_signature",
            "coverage_field": (
                "affected_place_ids"
                if domain.domain_id == "economy_law"
                else ""
            ),
            "expected_scope": (
                "service_system"
                if domain.domain_id == "economy_law"
                else "place_population"
            ),
            "signature_components": [
                "scale_scope",
                "served_population_band",
                "workforce_band",
                "service_reach_band",
                "throughput_band",
                "price_basis",
                "scarcity_level",
                "reserve_horizon",
                "demand_pressure",
            ],
        }
    if resource_enabled:
        metadata["resource_dependency_contract"] = {
            "schema_version": "rpg_world_resource_dependency_contract_v1",
            "required": True,
            "provider_field": "resource_provider_ids",
            "consumer_field": "resource_consumer_ids",
            "signature_field": "resource_dependency_signature",
            "signature_components": [
                "resource_class",
                "supply_mode",
                "dependency_strength",
                "substitute_class",
                "bottleneck_type",
                "depletion_horizon",
                "failure_consequence",
                "recovery_mode",
            ],
        }
    return metadata


def _effective_dependencies(
    domain: DomainDefinition,
    capability_flags: Mapping[str, bool],
) -> tuple[str, ...]:
    """Make every cross-domain typed reference available to the generator.

    Profile fields are validated against the dependency topics passed into a single
    generation job. Authors should not have to duplicate every reference target in
    the handwritten dependency list, and self-references such as parent_place_id do
    not require a separate graph edge.
    """

    reference_domains = (
        target
        for field in _domain_fields(domain, capability_flags)
        if field.value_type in {"entity_ref", "entity_ref_list"}
        for target in field.allowed_target_domains
        if target != domain.domain_id
    )
    return tuple(dict.fromkeys((*domain.dependencies, *reference_domains)))


def _domain_node(
    domain: DomainDefinition,
    *,
    depth: str,
    capability_flags: Mapping[str, bool],
) -> CampaignTopicNode:
    metadata = _field_metadata(domain, capability_flags, depth=depth)
    presentation = _record(metadata.get("presentation"))
    page_kind = str(presentation.get("page_kind") or "document")
    category = domain.category
    if category == "domain":
        category = domain.domain_id if page_kind == "collection" else "lore"
    probe = CampaignTopicNode(
        topic_id=domain.domain_id,
        title=domain.title,
        category=category,
        dependencies=_effective_dependencies(domain, capability_flags),
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
    causal_contract = causal_generation_contract(probe)
    if causal_contract:
        metadata["causal_generation_contract"] = causal_contract
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
    capability_flags = {
        **profile.runtime_capability_defaults.as_dict(),
        **dict(runtime_capabilities or {}),
    }
    domain_nodes = tuple(
        _domain_node(domain, depth=depth, capability_flags=capability_flags)
        for domain in profile.domains
    )
    domain_ids = tuple(domain.domain_id for domain in profile.domains)
    enabled_network_domains = sorted(
        _NETWORK_DOMAIN_IDS.intersection(domain_ids)
        if capability_flags.get(_NETWORK_CAPABILITY)
        else set()
    )
    enabled_spatial_domains = sorted(_SPATIAL_DOMAIN_IDS.intersection(domain_ids))
    enabled_economic_scale_domains = sorted(
        _ECONOMIC_SCALE_DOMAIN_IDS.intersection(domain_ids)
    )
    enabled_resource_domains = sorted(_RESOURCE_DOMAIN_IDS.intersection(domain_ids))
    base_profile_hash = str(
        dict(profile.provenance).get("base_profile_hash") or profile.content_hash
    )
    metadata: dict[str, Any] = {
        "genre_profile_id": profile.profile_id,
        "genre_profile_version": profile.version,
        "resolved_profile_hash": base_profile_hash,
        "compiled_profile_hash": profile.content_hash,
        "resolved_profile": profile.as_dict(),
        "genre_tags": list(profile.genre_tags),
        "tone": str(tone or ""),
        "starting_location": str(starting_location or ""),
        "background_expansion": bool(background_expansion),
        "runtime_capabilities": capability_flags,
        "launch_requirements": profile.launch_requirements.as_dict(),
        "planning_contract": planning_contract_metadata(),
        "mission_signature_contract": {
            "schema_version": "rpg_world_mission_signature_contract_v1",
            "domain_ids": sorted(_MISSION_DOMAIN_IDS),
        },
        "actor_incentive_contract": {
            "schema_version": "rpg_world_actor_incentive_contract_v1",
            "domain_ids": sorted(_ACTOR_DOMAIN_IDS),
        },
    }
    if enabled_network_domains:
        metadata["network_constraint_contract"] = {
            "schema_version": "rpg_world_network_constraint_contract_v1",
            "capability": _NETWORK_CAPABILITY,
            "domain_ids": enabled_network_domains,
            "required_before_launch": True,
        }
    if enabled_spatial_domains:
        place_node = next(
            node for node in domain_nodes if node.topic_id in enabled_spatial_domains
        )
        metadata["spatial_route_contract"] = {
            "schema_version": "rpg_world_spatial_route_contract_v1",
            "domain_ids": enabled_spatial_domains,
            "required_before_launch": True,
            "depth": str(depth or "standard"),
            "place_count": place_node.target_count,
            "minimum_route_count": minimum_route_count(
                place_node.target_count,
                depth,
            ),
        }
    if enabled_economic_scale_domains:
        metadata["economic_scale_contract"] = {
            "schema_version": "rpg_world_economic_scale_contract_v1",
            "domain_ids": enabled_economic_scale_domains,
            "required_before_launch": True,
            "minimum_band_diversity": 2,
        }
    if enabled_resource_domains:
        metadata["resource_dependency_contract"] = {
            "schema_version": "rpg_world_resource_dependency_contract_v1",
            "domain_ids": enabled_resource_domains,
            "required_before_launch": True,
            "minimum_resource_class_count": 2,
            "requires_chokepoint": True,
            "requires_substitute": True,
        }
    graph = CampaignTopicGraph(
        graph_version="rpg_profile_topic_graph_v2",
        campaign_template=str(campaign_template or profile.profile_id),
        depth=str(depth or "standard"),  # type: ignore[arg-type]
        nodes=(*domain_nodes, *_pipeline_nodes(domain_ids)),
        metadata=metadata,
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
    for contract_name in (
        "network_constraint_contract",
        "spatial_route_contract",
        "economic_scale_contract",
        "resource_dependency_contract",
    ):
        contract = _record(graph.metadata.get(contract_name))
        if bool(contract.get("required_before_launch")):
            selected.update(
                str(topic_id)
                for topic_id in contract.get("domain_ids") or ()
                if str(topic_id)
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
