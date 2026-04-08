"""Merge generated world bootstrap proposals into builder state."""
from __future__ import annotations

import copy
from typing import Optional


def merge_generated_package_into_setup(
    setup: dict,
    generated: dict,
    *,
    keep_existing_seeds: bool = True,
    locked_ids: Optional[list[str]] = None,
) -> dict:
    """Merge a generated package into the canonical setup.

    Rules:
    - If ``keep_existing_seeds=True``, do not overwrite user-authored entities
    - Merge by ID when explicit
    - Locked generated entities survive regeneration
    - Opening patch fills missing opening fields, doesn't overwrite explicit user fields

    Returns new setup dict (does not mutate input).
    """
    result = copy.deepcopy(setup)
    locked = set(locked_ids or [])

    # Merge characters (npc_seeds)
    result["npc_seeds"] = _merge_entity_list(
        existing=result.get("npc_seeds", []),
        generated=generated.get("characters", []),
        id_field="npc_id",
        keep_existing=keep_existing_seeds,
        locked=locked,
    )

    # Merge locations
    result["locations"] = _merge_entity_list(
        existing=result.get("locations", []),
        generated=generated.get("locations", []),
        id_field="location_id",
        keep_existing=keep_existing_seeds,
        locked=locked,
    )

    # Merge factions
    result["factions"] = _merge_entity_list(
        existing=result.get("factions", []),
        generated=generated.get("factions", []),
        id_field="faction_id",
        keep_existing=keep_existing_seeds,
        locked=locked,
    )

    # Merge lore_entries into lore_constraints
    gen_lore = generated.get("lore_entries", [])
    if gen_lore:
        existing_lore = list(result.get("lore_constraints", []))
        existing_names = {
            _norm(lc.get("name", "")) for lc in existing_lore
        }
        for entry in gen_lore:
            name = entry.get("title", "") or entry.get("name", "")
            if not name or _norm(name) in existing_names:
                continue
            existing_lore.append({
                "name": name,
                "description": entry.get("content", entry.get("description", "")),
                "authority": "generated",
            })
            existing_names.add(_norm(name))
        result["lore_constraints"] = existing_lore

    # Merge rumors into canon_notes
    gen_rumors = generated.get("rumors", [])
    if gen_rumors:
        existing_notes = list(result.get("canon_notes", []))
        existing_texts = {_norm(n) for n in existing_notes}
        for rumor in gen_rumors:
            text = rumor.get("text", "")
            if not text or _norm(text) in existing_texts:
                continue
            reliability = rumor.get("reliability", "unknown")
            note = f"[Rumor ({reliability})] {text}"
            existing_notes.append(note)
            existing_texts.add(_norm(text))
        result["canon_notes"] = existing_notes

    # Apply opening patch — fills missing fields only
    opening_patch = generated.get("opening_patch")
    if opening_patch and isinstance(opening_patch, dict):
        existing_opening = dict(result.get("opening", {}))
        for key, value in opening_patch.items():
            if value and not existing_opening.get(key):
                existing_opening[key] = value
        result["opening"] = existing_opening

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    """Normalize text for comparison."""
    return " ".join((text or "").lower().strip().split())


def _merge_entity_list(
    existing: list[dict],
    generated: list[dict],
    id_field: str,
    keep_existing: bool,
    locked: set[str],
) -> list[dict]:
    """Merge generated entities into existing list.

    - Existing entities are preserved when ``keep_existing`` is True
    - Generated entities with matching IDs update only if not keep_existing
    - Locked IDs are always preserved from existing (never overwritten)
    - New generated entities are appended
    """
    existing_by_id: dict[str, dict] = {}
    for entity in existing:
        eid = entity.get(id_field, "")
        if eid:
            existing_by_id[eid] = entity

    result: list[dict] = []
    seen_ids: set[str] = set()

    # First pass: existing entities
    for entity in existing:
        eid = entity.get(id_field, "")
        result.append(dict(entity))
        if eid:
            seen_ids.add(eid)

    # Second pass: generated entities
    for gen_entity in generated:
        gen_id = gen_entity.get(id_field, "")
        if gen_id in seen_ids:
            # Entity exists — only update if not keep_existing and not locked
            if not keep_existing and gen_id not in locked:
                result = [
                    dict(gen_entity) if e.get(id_field) == gen_id else e
                    for e in result
                ]
        else:
            # New entity — append
            result.append(dict(gen_entity))
            if gen_id:
                seen_ids.add(gen_id)

    return result
