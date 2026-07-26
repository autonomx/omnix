"""Provider-facing generation contracts for causal World Forge domains."""
from __future__ import annotations

from typing import Any

from .world_forge_contract import CampaignTopicNode

_CAUSAL_TOPICS = frozenset(
    {
        "history_timeline",
        "regions",
        "places",
        "groups",
        "cultures",
        "actors",
        "causal_links",
    }
)


def causal_generation_contract(node: CampaignTopicNode) -> dict[str, Any]:
    """Return constraints embedded in provider payload metadata."""

    if node.topic_id not in _CAUSAL_TOPICS:
        return {}
    rules = [
        "Use only entity IDs supplied by dependencies or the current topic registry.",
        "Do not place invented IDs inside structured objects or prose.",
        "Treat typed historical references as causal constraints, not loose inspiration.",
        "Keep canonical causes in structured fields; presentation prose may only explain them.",
        "Distinguish a continuing effect from one that terminated, reversed, was absorbed, concealed, or forgotten.",
    ]
    if node.topic_id == "history_timeline":
        rules.extend(
            [
                "cause_event_ids may reference only earlier events allocated in this topic.",
                "Every continuing legacy must name a concrete present-day trace.",
            ]
        )
    elif node.topic_id == "causal_links":
        rules.extend(
            [
                "Every link must connect supplied historical-event IDs to one supplied effect entity ID.",
                "The mechanism must explain the material, political, economic, geographic, or cultural process.",
                "Do not merely restate the effect_type as the mechanism.",
                "Use distinct cause/effect pairs across registry slots.",
            ]
        )
    else:
        rules.extend(
            [
                "Backward-pointing origin fields must agree with the supplied history timeline.",
                "Do not reinterpret an allocated founding or formation event.",
            ]
        )
    return {
        "schema_version": "rpg_world_forge_causal_generation_v1",
        "topic_id": node.topic_id,
        "rules": rules,
        "authoritative_fields": [
            str(row.get("field_id") or "")
            for row in node.metadata.get("field_definitions") or ()
            if str(row.get("semantic_role") or "")
            in {
                "caused_by",
                "formed_by",
                "founded_by",
                "originated_in",
                "origin_region",
                "descended_from",
                "shaped_by",
                "cultural_affiliation",
                "cause",
                "effect",
            }
        ],
    }


__all__ = ["causal_generation_contract"]
