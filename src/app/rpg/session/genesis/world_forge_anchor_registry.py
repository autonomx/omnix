"""Deterministic allocation of major global World Forge anchor identities."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from .world_forge_contract import CampaignTopicGraph


@dataclass(frozen=True)
class AnchorSlot:
    id: str
    domain_id: str
    anchor_kind: str
    slot_index: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "domain_id": self.domain_id,
            "anchor_kind": self.anchor_kind,
            "slot_index": self.slot_index,
        }


_ANCHOR_DOMAINS = {
    "regions": ("region", "region", 12),
    "places": ("major_settlement", "places", 6),
    "groups": ("major_institution", "groups", 6),
    "cultures": ("major_culture", "cultures", 6),
    "actors": ("historical_actor", "actors", 4),
    "history_timeline": ("historical_event", "history_timeline", 10),
}


def _registry_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def allocate_global_anchor_registry(
    graph: CampaignTopicGraph,
    *,
    seed: int,
    world_key: str,
) -> dict[str, Any]:
    """Allocate stable IDs for major anchors without inventing names or lore."""

    node_map = graph.node_map()
    anchors: list[dict[str, Any]] = []
    for domain_id, (anchor_kind, prefix, maximum) in _ANCHOR_DOMAINS.items():
        node = node_map.get(domain_id)
        if node is None:
            continue
        count = min(maximum, max(0, int(node.target_count)))
        anchors.extend(
            AnchorSlot(
                id=f"ent:{prefix}:{index:03d}",
                domain_id=domain_id,
                anchor_kind=anchor_kind,
                slot_index=index,
            ).as_dict()
            for index in range(1, count + 1)
        )
    payload: dict[str, Any] = {
        "schema_version": "rpg_world_forge_anchor_registry_v1",
        "revision": 1,
        "internal": True,
        "seed": int(seed),
        "world_key": str(world_key),
        "anchors": anchors,
    }
    payload["registry_hash"] = _registry_hash(payload)
    issues = validate_global_anchor_registry(payload)
    if issues:
        raise ValueError("invalid_global_anchor_registry:" + ",".join(issues))
    return payload


def validate_global_anchor_registry(value: Mapping[str, Any]) -> tuple[str, ...]:
    anchors = value.get("anchors")
    if not isinstance(anchors, list):
        return ("anchor_registry_array_required",)
    issues: list[str] = []
    seen: set[str] = set()
    for row in anchors:
        if not isinstance(row, Mapping):
            issues.append("anchor_slot_object_required")
            continue
        anchor_id = str(row.get("id") or "")
        domain_id = str(row.get("domain_id") or "")
        definition = _ANCHOR_DOMAINS.get(domain_id)
        if definition is None:
            issues.append(f"unsupported_anchor_domain:{domain_id}")
            continue
        expected_prefix = f"ent:{definition[1]}:"
        if not anchor_id.startswith(expected_prefix):
            issues.append(f"anchor_prefix_mismatch:{anchor_id}:{domain_id}")
        if anchor_id in seen:
            issues.append(f"duplicate_anchor_id:{anchor_id}")
        seen.add(anchor_id)
    return tuple(dict.fromkeys(issues))


def anchor_slice_for_domain(
    domain_id: str,
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    anchors = [
        dict(row)
        for row in registry.get("anchors") or ()
        if isinstance(row, Mapping) and str(row.get("domain_id") or "") == domain_id
    ]
    return {
        "schema_version": str(registry.get("schema_version") or ""),
        "registry_hash": str(registry.get("registry_hash") or ""),
        "anchors": anchors,
    }


__all__ = [
    "AnchorSlot",
    "allocate_global_anchor_registry",
    "anchor_slice_for_domain",
    "validate_global_anchor_registry",
]
