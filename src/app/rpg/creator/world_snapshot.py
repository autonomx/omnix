"""Phase 2.5 — World Snapshot + Graph Diff.

Provides deterministic snapshot wrapping around the existing world
inspection result, plus graph/entity diff computation.

All functions accept plain dicts and return plain dicts suitable for
JSON serialization.  Nothing here mutates the setup payload.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from .world_graph import (
    build_entity_inspector,
    build_simulation_summary,
    build_world_graph,
)


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------


def build_world_snapshot(
    setup_payload: dict[str, Any],
    label: str | None = None,
) -> dict[str, Any]:
    """Build a full snapshot wrapper from a setup payload.

    Returns
    -------
    dict
        ``{"snapshot_id": ..., "label": ..., "created_at": ...,
           "graph": {...}, "simulation": {...}, "inspector": {...},
           "summary": {"node_count": int, "edge_count": int}}``
    """
    graph = build_world_graph(setup_payload)
    simulation = build_simulation_summary(setup_payload)
    inspector = build_entity_inspector(setup_payload)

    return {
        "snapshot_id": f"snap_{uuid.uuid4().hex[:8]}",
        "label": label or "Snapshot",
        "created_at": time.time(),
        "graph": graph,
        "simulation": simulation,
        "inspector": inspector,
        "summary": {
            "node_count": len(graph.get("nodes", [])),
            "edge_count": len(graph.get("edges", [])),
        },
    }


# ---------------------------------------------------------------------------
# Graph diff
# ---------------------------------------------------------------------------


def _normalize_meta(meta: Any) -> dict[str, Any]:
    """Normalize a node meta dict for comparison.

    Sorts any list values so ordering noise is ignored.
    """
    if not isinstance(meta, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in sorted(meta.items()):
        if isinstance(v, list):
            try:
                out[k] = sorted(v)
            except TypeError:
                out[k] = v
        else:
            out[k] = v
    return out


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    """Return a stable identity tuple for an edge."""
    return (
        str(edge.get("source", "")),
        str(edge.get("target", "")),
        str(edge.get("type", "")),
    )


def compute_graph_diff(
    before_graph: dict[str, Any] | None,
    after_graph: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute added/removed/changed nodes and added/removed edges.

    Parameters
    ----------
    before_graph, after_graph :
        Each has shape ``{"nodes": [...], "edges": [...]}``.

    Returns
    -------
    dict
        ``{"nodes": {"added": [...], "removed": [...], "changed": [...]},
           "edges": {"added": [...], "removed": [...]},
           "summary": [...]}``
    """
    before_graph = before_graph or {"nodes": [], "edges": []}
    after_graph = after_graph or {"nodes": [], "edges": []}

    # --- Node diff ---
    before_nodes: dict[str, dict[str, Any]] = {
        n["id"]: n for n in (before_graph.get("nodes") or []) if "id" in n
    }
    after_nodes: dict[str, dict[str, Any]] = {
        n["id"]: n for n in (after_graph.get("nodes") or []) if "id" in n
    }

    added_ids = sorted(set(after_nodes) - set(before_nodes))
    removed_ids = sorted(set(before_nodes) - set(after_nodes))

    changed: list[dict[str, Any]] = []
    for nid in sorted(set(before_nodes) & set(after_nodes)):
        b = before_nodes[nid]
        a = after_nodes[nid]
        changed_fields: list[str] = []
        if b.get("label") != a.get("label"):
            changed_fields.append("label")
        if b.get("type") != a.get("type"):
            changed_fields.append("type")
        if _normalize_meta(b.get("meta")) != _normalize_meta(a.get("meta")):
            changed_fields.append("meta")
        if changed_fields:
            changed.append({"id": nid, "fields": sorted(changed_fields)})

    # --- Edge diff ---
    before_edges = {_edge_key(e) for e in (before_graph.get("edges") or [])}
    after_edges = {_edge_key(e) for e in (after_graph.get("edges") or [])}

    added_edges = [
        {"source": k[0], "target": k[1], "type": k[2]}
        for k in sorted(after_edges - before_edges)
    ]
    removed_edges = [
        {"source": k[0], "target": k[1], "type": k[2]}
        for k in sorted(before_edges - after_edges)
    ]

    # --- Summary ---
    summary = summarize_graph_diff(
        added_ids, removed_ids, changed, added_edges, removed_edges,
    )

    return {
        "nodes": {
            "added": added_ids,
            "removed": removed_ids,
            "changed": changed,
        },
        "edges": {
            "added": added_edges,
            "removed": removed_edges,
        },
        "summary": summary,
    }


def summarize_graph_diff(
    added_ids: list[str],
    removed_ids: list[str],
    changed: list[dict[str, Any]],
    added_edges: list[dict[str, Any]],
    removed_edges: list[dict[str, Any]],
) -> list[str]:
    """Return human-readable summary strings."""
    lines: list[str] = []

    def _pl(n: int, word: str) -> str:
        return f"{n} {word}" if n == 1 else f"{n} {word}s"

    if added_ids:
        lines.append(f"{_pl(len(added_ids), 'node')} added")
    if removed_ids:
        lines.append(f"{_pl(len(removed_ids), 'node')} removed")
    if changed:
        lines.append(f"{_pl(len(changed), 'node')} changed")
    if added_edges:
        lines.append(f"{_pl(len(added_edges), 'edge')} added")
    if removed_edges:
        lines.append(f"{_pl(len(removed_edges), 'edge')} removed")
    return lines


# ---------------------------------------------------------------------------
# Entity history diff
# ---------------------------------------------------------------------------


def compute_entity_history_diff(
    before_inspector: dict[str, Any] | None,
    after_inspector: dict[str, Any] | None,
    entity_id: str,
) -> dict[str, Any]:
    """Compute per-entity field diff between two inspector outputs.

    Parameters
    ----------
    before_inspector, after_inspector :
        Each has shape ``{"entities": {"npc_mara_voss": {...}, ...}}``.
    entity_id :
        The entity to inspect.

    Returns
    -------
    dict
        ``{"entity_id": ..., "exists_before": bool, "exists_after": bool,
           "diff": {"changed_fields": [...], "before": {...}, "after": {...},
                    "related_added": [...], "related_removed": [...]}}``
    """
    before_entities = (before_inspector or {}).get("entities") or {}
    after_entities = (after_inspector or {}).get("entities") or {}

    before_detail = before_entities.get(entity_id)
    after_detail = after_entities.get(entity_id)

    exists_before = before_detail is not None
    exists_after = after_detail is not None

    if not exists_before and not exists_after:
        return {
            "entity_id": entity_id,
            "exists_before": False,
            "exists_after": False,
            "diff": {
                "changed_fields": [],
                "before": {},
                "after": {},
                "related_added": [],
                "related_removed": [],
            },
        }

    before_detail = before_detail or {}
    after_detail = after_detail or {}

    # Find changed fields
    all_keys = sorted(set(list(before_detail.keys()) + list(after_detail.keys())))
    changed_fields: list[str] = []
    for key in all_keys:
        bv = before_detail.get(key)
        av = after_detail.get(key)
        if _values_differ(bv, av):
            changed_fields.append(key)

    # Compute related entity changes via related_threads
    before_related = _extract_related_ids(before_detail)
    after_related = _extract_related_ids(after_detail)
    related_added = sorted(after_related - before_related)
    related_removed = sorted(before_related - after_related)

    return {
        "entity_id": entity_id,
        "exists_before": exists_before,
        "exists_after": exists_after,
        "diff": {
            "changed_fields": changed_fields,
            "before": before_detail,
            "after": after_detail,
            "related_added": related_added,
            "related_removed": related_removed,
        },
    }


def _values_differ(a: Any, b: Any) -> bool:
    """Compare two values, treating list ordering as insignificant where safe."""
    if isinstance(a, list) and isinstance(b, list):
        try:
            return sorted(a) != sorted(b)
        except TypeError:
            return a != b
    return a != b


def _extract_related_ids(detail: dict[str, Any]) -> set[str]:
    """Extract related entity ids from an inspector detail record."""
    ids: set[str] = set()
    for rt in detail.get("related_threads") or []:
        if isinstance(rt, dict):
            tid = rt.get("thread_id", "")
            if tid:
                ids.add(tid)
    for m in detail.get("members") or []:
        if isinstance(m, dict):
            nid = m.get("npc_id", "")
            if nid:
                ids.add(nid)
    for r in detail.get("residents") or []:
        if isinstance(r, dict):
            nid = r.get("npc_id", "")
            if nid:
                ids.add(nid)
    for fid in detail.get("involved_factions") or []:
        if isinstance(fid, str) and fid:
            ids.add(fid)
    for lid in detail.get("related_locations") or []:
        if isinstance(lid, str) and lid:
            ids.add(lid)
    for eid in detail.get("involved_entities") or []:
        if isinstance(eid, str) and eid:
            ids.add(eid)
    for fid in detail.get("faction_ids") or []:
        if isinstance(fid, str) and fid:
            ids.add(fid)
    for lid in detail.get("location_ids") or []:
        if isinstance(lid, str) and lid:
            ids.add(lid)
    return ids
