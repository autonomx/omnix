"""Profile-aware deterministic topic generation for offline tests and fallback."""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .world_forge_actor_incentives import deterministic_actor_incentive_signature
from .world_forge_contract import CampaignTopicNode
from .world_forge_generation import GeneratedTopic
from .world_forge_network_constraints import (
    deterministic_network_constraint_signature,
)

_DISTINCTIONS = (
    "Ember", "Tide", "Glass", "Copper", "Ash", "Lantern",
    "Harbor", "Thorn", "Mirror", "Stone", "Violet", "North",
)
_OPTIONAL_CAUSAL_REFERENCE_ROLES = frozenset(
    {
        "caused_by", "formed_by", "founded_by", "originated_in",
        "origin_region", "descended_from", "shaped_by", "cultural_affiliation",
    }
)
_OPTIONAL_ARC_FIELDS = frozenset({"campaign_arc_id", "arc_role", "arc_sequence"})
_MISSION_ACTIVITIES = (
    "investigate",
    "recover",
    "protect",
    "negotiate",
    "expose",
    "disrupt",
)
_MISSION_TARGETS = (
    "evidence_chain",
    "scarce_resource",
    "endangered_witness",
    "contested_route",
    "hidden_controller",
    "unstable_system",
)
_MISSION_LOCATIONS = (
    "public_hub",
    "restricted_site",
    "contested_transit",
    "remote_perimeter",
)
_MISSION_PRINCIPALS = (
    "local_sponsor",
    "institutional_officer",
    "affected_resident",
    "independent_broker",
    "reluctant_insider",
)
_MISSION_ANTAGONISTS = (
    "institutional_rival",
    "resource_controller",
    "covert_operator",
    "environmental_hazard",
    "divided_authority",
    "opportunistic_threat",
    "compromised_ally",
)
_MISSION_PRESSURES = (
    "time_window",
    "resource_depletion",
    "public_exposure",
    "escalating_violence",
    "loss_of_access",
    "competing_claim",
    "evidence_decay",
    "trust_collapse",
)
_MISSION_RESOLUTIONS = (
    "document",
    "negotiate",
    "extract",
    "repair",
    "redirect",
    "expose",
    "contain",
    "sabotage",
)
_MISSION_CONSEQUENCES = (
    "access_shift",
    "trust_shift",
    "resource_shift",
    "authority_shift",
    "route_shift",
    "knowledge_shift",
    "security_shift",
    "faction_shift",
    "infrastructure_shift",
)


def _slug(value: str) -> str:
    return "_".join("".join(ch.casefold() if ch.isalnum() else " " for ch in value).split()) or "entry"


def _definitions(node: CampaignTopicNode) -> tuple[dict[str, Any], ...]:
    value = node.metadata.get("field_definitions")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


def _brief_anchor(context: Mapping[str, Any]) -> str:
    brief = context.get("world_brief")
    values: list[str] = []
    if isinstance(brief, Mapping):
        values.extend(str(brief.get(field) or "") for field in ("title", "description", "genre"))
    values.extend(str(context.get(field) or "") for field in ("campaign_template", "genre", "tone"))
    tokens: list[str] = []
    for token in re.findall(r"[A-Za-z0-9]{4,}", " ".join(values)):
        lowered = token.casefold()
        if lowered not in {value.casefold() for value in tokens}:
            tokens.append(token)
    return " ".join(tokens[:6]) or "Deterministic Campaign"


def _known_by_domain(dependencies: Mapping[str, GeneratedTopic]) -> dict[str, tuple[str, ...]]:
    known: dict[str, tuple[str, ...]] = {}
    for domain_id, topic in dependencies.items():
        known[str(domain_id)] = tuple(
            str(entity.get("id") or entity.get("entity_id") or "")
            for entity in topic.entities
            if str(entity.get("id") or entity.get("entity_id") or "")
        )
    return known


def _reference_candidates(
    definition: Mapping[str, Any],
    known: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...]:
    return tuple(
        entity_id
        for domain_id in definition.get("allowed_target_domains") or ()
        for entity_id in known.get(str(domain_id), ())
    )


def _string_value(field_id: str, *, name: str, anchor: str, index: int) -> str:
    distinction = _DISTINCTIONS[index % len(_DISTINCTIONS)]
    templates = {
        "rule": f"Within {anchor}, {name} follows the {distinction} constraint: every advantage consumes a visible resource or creates a traceable obligation.",
        "current_pressure": f"{name} faces a {distinction.lower()} shortage that will disrupt a named route in {anchor} during the next operational cycle.",
        "current_objective": f"{name} intends to secure the {distinction} junction before a rival group can redirect its benefits across {anchor}.",
        "goal": f"{name} seeks to restore the {distinction} network before the next public assembly in {anchor}.",
        "dependency": f"{name} depends on calibrated {distinction.lower()} components controlled by another institution in {anchor}.",
        "next_action": f"At the next tick, {name} dispatches a two-person team to inspect the {distinction} marker and record who interferes.",
        "next_tick_change": f"During the next tick, the {distinction} condition advances and changes access, prices, or patrol patterns around {name}.",
        "failure_response": f"If blocked, {name} closes the {distinction} route, shifts supplies, and publicly blames the faction that benefits from the delay.",
        "escalation_condition": f"The pressure escalates when the {distinction} reserve falls below one day of local demand or a second route is lost.",
        "function_in_setting": f"{name} gives {anchor} a distinct {distinction.lower()} institution whose rules affect travel, bargaining, and public trust.",
        "former_purpose": f"Before the present crisis, {name} served as the {distinction} exchange for freight, records, and civic announcements in {anchor}.",
        "current_hazard": f"A damaged {distinction.lower()} regulator releases intermittent heat, noise, and contaminated runoff whenever the old machinery cycles.",
        "scarcity": f"Only three days of the {distinction.lower()} reserve remain available to ordinary residents at current demand.",
        "failure_effect": f"If the reserve fails, the {distinction} district loses transport, clean water, and reliable night lighting.",
        "cause": f"The condition began when the {distinction} containment system fractured during a recorded emergency in {anchor}.",
        "capability": f"The {distinction} system grants precise environmental sensing within a limited operational radius.",
        "cost": f"Each use consumes a replaceable {distinction.lower()} cell and causes a temporary sensory penalty.",
        "failure_mode": f"Under overload, the {distinction} system emits false readings and locks until manually recalibrated.",
        "source": f"The {distinction} effect originates in a documented material, social, or technical process unique to {anchor}.",
    }
    return templates.get(
        field_id,
        f"{name} defines {field_id.replace('_', ' ')} through the {distinction} practice, a specific institution, material, and consequence grounded in {anchor}.",
    )


def _mission_signature(entity_kind: str, index: int) -> dict[str, Any]:
    return {
        "activity": _MISSION_ACTIVITIES[index % len(_MISSION_ACTIVITIES)],
        "target": _MISSION_TARGETS[(index * 5 + 1) % len(_MISSION_TARGETS)],
        "location": _MISSION_LOCATIONS[(index * 3 + 1) % len(_MISSION_LOCATIONS)],
        "principal_actor": _MISSION_PRINCIPALS[(index * 2 + 1) % len(_MISSION_PRINCIPALS)],
        "antagonist": _MISSION_ANTAGONISTS[(index * 3 + 2) % len(_MISSION_ANTAGONISTS)],
        "pressure": _MISSION_PRESSURES[(index * 5 + 3) % len(_MISSION_PRESSURES)],
        "resolution_modes": [
            _MISSION_RESOLUTIONS[index % len(_MISSION_RESOLUTIONS)],
            _MISSION_RESOLUTIONS[(index * 3 + 2) % len(_MISSION_RESOLUTIONS)],
        ],
        "consequence_type": _MISSION_CONSEQUENCES[
            (index * 7 + len(entity_kind)) % len(_MISSION_CONSEQUENCES)
        ],
    }


def _structured_value(
    field_id: str,
    *,
    name: str,
    anchor: str,
    index: int,
    entity_kind: str,
) -> dict[str, Any]:
    if field_id == "mission_signature":
        return _mission_signature(entity_kind, index)
    if field_id == "incentive_signature":
        return deterministic_actor_incentive_signature(index)
    if field_id == "network_constraint_signature":
        return deterministic_network_constraint_signature(index)
    distinction = _DISTINCTIONS[index % len(_DISTINCTIONS)]
    labels = {
        "observable_consequences": "visible consequence",
        "access_routes": "access route",
        "observable_evidence": "observable evidence",
        "observable_signs": "observable sign",
        "resources": "resource",
        "dependencies": "dependency",
        "internal_divisions": "internal division",
        "reaction_conditions": "reaction condition",
        "knowledge_limits": "knowledge limit",
        "initial_evidence": "initial evidence",
        "player_choices": "player choice",
        "aftermath": "aftermath",
        "recoverable_evidence": "recoverable evidence",
        "effects": "effect",
        "limitations": "limitation",
        "costs": "cost",
        "limits": "limit",
        "access_conditions": "access condition",
    }
    label = labels.get(field_id, field_id.replace("_", " "))
    return {
        "detail": f"{name}'s {label} is marked by the {distinction} signal, logged by a named local witness in {anchor}.",
        "consequence": f"Ignoring this {label} changes access, trust, or material supply during the next deterministic world tick.",
    }


def _value_for_field(
    definition: Mapping[str, Any],
    *,
    name: str,
    anchor: str,
    index: int,
    known: Mapping[str, tuple[str, ...]],
    entity_kind: str,
) -> Any:
    field_id = str(definition.get("field_id") or "")
    value_type = str(definition.get("value_type") or "string")
    if field_id in _OPTIONAL_ARC_FIELDS:
        return None
    candidates = _reference_candidates(definition, known)
    if field_id == "name":
        return name
    if value_type == "string":
        return _string_value(field_id, name=name, anchor=anchor, index=index)
    if value_type == "structured_object":
        return _structured_value(
            field_id,
            name=name,
            anchor=anchor,
            index=index,
            entity_kind=entity_kind,
        )
    if value_type == "entity_ref":
        return candidates[index % len(candidates)] if candidates else ""
    if value_type == "entity_ref_list":
        if not candidates:
            return []
        width = min(2, len(candidates))
        return [candidates[(index + offset) % len(candidates)] for offset in range(width)]
    if value_type == "enum":
        values = tuple(str(value) for value in definition.get("enum_values") or ())
        return values[index % len(values)] if values else "defined"
    if value_type == "integer":
        return index + 1
    if value_type == "number":
        return float(index + 1)
    if value_type == "boolean":
        return index % 2 == 0
    return _string_value(field_id, name=name, anchor=anchor, index=index)


def _authoritative_ids(node: CampaignTopicNode) -> tuple[str, ...]:
    value = node.metadata.get("authoritative_entity_ids")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value if str(item))


def _fixture_identity(
    node: CampaignTopicNode,
    *,
    campaign_context: Mapping[str, Any],
    entity_kind: str,
    anchor: str,
    index: int,
) -> tuple[str, str]:
    starting_location = str(campaign_context.get("starting_location") or "").strip()
    is_place_domain = (
        node.topic_id in {"places", "locations", "settlements"}
        or entity_kind in {"place", "location", "settlement"}
    )
    authoritative_ids = _authoritative_ids(node)
    authoritative_id = authoritative_ids[index] if index < len(authoritative_ids) else ""
    if index == 0 and starting_location and is_place_domain:
        local_id = starting_location.split(":", 1)[-1]
        name = local_id.replace("_", " ").replace("-", " ").title()
        return authoritative_id or f"{_slug(entity_kind)}:{_slug(local_id)}", name
    distinction = _DISTINCTIONS[index % len(_DISTINCTIONS)]
    name = f"{anchor} {distinction} {entity_kind.replace('_', ' ').title()}"
    entity_id = authoritative_id or f"{_slug(entity_kind)}:{_slug(distinction)}_{index + 1}"
    return entity_id, name


def generate_deterministic_profile_topic(
    node: CampaignTopicNode,
    *,
    campaign_context: Mapping[str, Any],
    dependency_topics: Mapping[str, GeneratedTopic],
) -> GeneratedTopic:
    """Produce schema-valid deterministic entities for a profile-defined domain."""

    definitions = _definitions(node)
    if not definitions:
        raise ValueError(f"profile_field_definitions_missing:{node.topic_id}")
    anchor = _brief_anchor(campaign_context)
    known = _known_by_domain(dependency_topics)
    entity_kind = str(node.metadata.get("entity_kind") or node.topic_id.rstrip("s"))
    entities: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    for index in range(node.target_count):
        entity_id, name = _fixture_identity(
            node,
            campaign_context=campaign_context,
            entity_kind=entity_kind,
            anchor=anchor,
            index=index,
        )
        entity: dict[str, Any] = {
            "id": entity_id,
            "kind": entity_kind,
            "visibility": node.visibility,
        }
        for definition in definitions:
            required = bool(definition.get("required", False))
            semantic_role = str(definition.get("semantic_role") or "").strip()
            if not required and semantic_role in _OPTIONAL_CAUSAL_REFERENCE_ROLES:
                continue
            value = _value_for_field(
                definition,
                name=name,
                anchor=anchor,
                index=index,
                known=known,
                entity_kind=entity_kind,
            )
            if value in (None, "", [], (), {}) and not required:
                continue
            entity[str(definition.get("field_id") or "")] = value
        entities.append(entity)
        rendered = "; ".join(
            f"{key.replace('_', ' ')}: {value}"
            for key, value in entity.items()
            if key not in {"id", "kind", "visibility"}
        )
        full_text = (
            f"{name} is deterministic profile fixture canon for {anchor}. {rendered}. "
            "Every listed value is structured and will be validated before presentation."
        )
        documents.append(
            {
                "document_id": f"document:{_slug(entity_id)}",
                "topic_id": node.topic_id,
                "title": name,
                "full_text": full_text,
                "summary_500": full_text[:500],
                "summary_120": full_text[:120],
                "facts": [],
                "entities": [entity_id],
                "relationships": [],
                "keywords": anchor.casefold().split(),
                "visibility": node.visibility,
                "canon_revision": 0,
            }
        )
    return GeneratedTopic(
        topic_id=node.topic_id,
        documents=tuple(documents),
        entities=tuple(entities),
        provenance={
            "generator": "deterministic_profile_fixture_v2",
            "profile_schema": node.metadata.get("schema_version"),
            "world_brief_anchor": anchor,
            "anchor_registry_hash": node.metadata.get("anchor_registry_hash"),
        },
    )
