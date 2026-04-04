"""Phase 7.9 — Pack Schema Helpers.

Helper schema constructors and canonicalization for adventure packs.
"""

from __future__ import annotations

import copy
from typing import Any

from .models import AdventurePack, PackContent, PackManifest, PackMetadata


def normalize_pack_dict(data: dict) -> dict:
    """Normalize a raw pack dictionary.

    - Normalize string fields (strip whitespace)
    - Ensure lists/dicts exist for all content fields
    - Apply deterministic ordering where possible
    """
    data = copy.deepcopy(data)

    # Normalize metadata strings
    meta = data.setdefault("metadata", {})
    for key in ("pack_id", "title", "version", "author", "description"):
        if key in meta and isinstance(meta[key], str):
            meta[key] = meta[key].strip()
    meta.setdefault("tags", [])
    meta.setdefault("requires_engine_version", "")
    meta.setdefault("metadata", {})

    # Normalize manifest
    manifest = data.setdefault("manifest", {})
    manifest.setdefault("manifest_id", "")
    manifest.setdefault("pack_id", meta.get("pack_id", ""))
    manifest.setdefault("content_version", meta.get("version", ""))
    manifest.setdefault("dependencies", [])
    manifest.setdefault("conflicts", [])
    manifest.setdefault("namespaces", [])
    manifest.setdefault("metadata", {})

    # Normalize content — ensure all list fields exist
    content = data.setdefault("content", {})
    for list_field in (
        "creator_facts",
        "setup_templates",
        "factions",
        "locations",
        "npcs",
        "threads",
        "arcs",
        "social_seeds",
        "reveal_seeds",
        "pacing_presets",
        "gm_presets",
    ):
        content.setdefault(list_field, [])
    content.setdefault("metadata", {})

    return data


def build_empty_pack(pack_id: str, title: str, version: str) -> AdventurePack:
    """Build a minimal valid adventure pack with empty content."""
    return AdventurePack(
        metadata=PackMetadata(
            pack_id=pack_id,
            title=title,
            version=version,
        ),
        manifest=PackManifest(
            manifest_id=f"{pack_id}_manifest",
            pack_id=pack_id,
            content_version=version,
        ),
        content=PackContent(),
    )


def namespace_content(pack: AdventurePack) -> AdventurePack:
    """Optionally prefix content IDs with pack namespace if configured.

    If the pack manifest has namespaces defined, prefix all content item
    IDs with the first namespace. Returns a new pack (does not mutate).
    """
    namespaces = pack.manifest.namespaces
    if not namespaces:
        return pack

    prefix = namespaces[0]
    new_pack = AdventurePack.from_dict(pack.to_dict())

    def _prefix_id(items: list[dict], id_key: str) -> list[dict]:
        result = []
        for item in items:
            item = dict(item)
            if id_key in item and isinstance(item[id_key], str):
                if not item[id_key].startswith(f"{prefix}:"):
                    item[id_key] = f"{prefix}:{item[id_key]}"
            result.append(item)
        return result

    c = new_pack.content
    c.factions = _prefix_id(c.factions, "faction_id")
    c.locations = _prefix_id(c.locations, "location_id")
    c.npcs = _prefix_id(c.npcs, "npc_id")
    c.threads = _prefix_id(c.threads, "thread_id")
    c.arcs = _prefix_id(c.arcs, "arc_id")

    return new_pack


def collect_pack_ids(pack: AdventurePack) -> dict[str, list[str]]:
    """Collect all content IDs from a pack, organized by type."""
    content = pack.content

    def _extract_ids(items: list[dict], id_key: str) -> list[str]:
        return [
            item[id_key]
            for item in items
            if isinstance(item.get(id_key), str)
        ]

    return {
        "factions": _extract_ids(content.factions, "faction_id"),
        "locations": _extract_ids(content.locations, "location_id"),
        "npcs": _extract_ids(content.npcs, "npc_id"),
        "threads": _extract_ids(content.threads, "thread_id"),
        "arcs": _extract_ids(content.arcs, "arc_id"),
    }
