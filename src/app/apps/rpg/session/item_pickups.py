"""Deterministic scene item pickup helpers for RPG sessions."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list

NODE_KEYS = ("item_nodes", "pickup_nodes", "resource_nodes")


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _node_id(node: dict[str, Any], ordinal: int) -> str:
    return _text(node.get("node_id") or node.get("id") or node.get("source_id"), f"scene_node_{ordinal + 1}")


def _node_remaining(node: dict[str, Any]) -> int:
    if node.get("depleted") is True:
        return 0
    for key in ("remaining", "uses", "quantity", "count"):
        value = node.get(key)
        if isinstance(value, (int, float)):
            return max(0, int(value))
    return 1


def _state_nodes(state: dict[str, Any]) -> tuple[dict[str, Any], str, list[Any]]:
    scene_state = _safe_dict(state.get("scene_state"))
    state["scene_state"] = scene_state
    for key in NODE_KEYS:
        if isinstance(scene_state.get(key), list):
            return scene_state, key, scene_state[key]
    scene_state["item_nodes"] = []
    return scene_state, "item_nodes", scene_state["item_nodes"]


def list_scene_item_nodes(state: dict[str, Any]) -> list[dict[str, Any]]:
    _container, _key, nodes = _state_nodes(state)
    listed: list[dict[str, Any]] = []
    for ordinal, raw in enumerate(_safe_list(nodes)):
        node = deepcopy(_safe_dict(raw))
        node["node_id"] = _node_id(node, ordinal)
        node["remaining"] = _node_remaining(node)
        node["depleted"] = node["remaining"] <= 0
        listed.append(node)
    return listed
