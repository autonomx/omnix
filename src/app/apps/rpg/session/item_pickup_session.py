"""Session-level scene item pickup bridge for RPG item actions.

This module keeps scene-item transfer route-free while adding session context
to the deterministic pickup helper. Routes, autoplay, or loadout-style actions
can call it to mutate inventory/scene nodes and receive trace-ready output.
"""
from __future__ import annotations


from typing import Any

from app.apps.rpg.session.item_pickups import list_scene_item_nodes
from app.apps.rpg.foundation.safe_values import safe_list as _safe_list


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def available_scene_pickups_for_session(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return non-depleted scene transfer nodes with deterministic summaries."""

    nodes = []
    for node in list_scene_item_nodes(state):
        if node.get("depleted") is True:
            continue
        nodes.append(
            {
                "node_id": _text(node.get("node_id")),
                "name": _text(node.get("name") or node.get("node_id")),
                "remaining": int(node.get("remaining") or 0),
                "has_explicit_outputs": bool(_safe_list(node.get("outputs") or node.get("items"))),
                "reward_table": _text(node.get("reward_table") or node.get("source_id") or node.get("table_id")),
            }
        )
    return nodes
