"""Targeted regeneration helpers for Creator UX partial refresh flows.

Phase 1.4 additions:
- Preview / apply regeneration modes
- Diff computation between before / after sections
- Replace vs merge strategies
- Single-item regeneration support
- Apply-token generation for safer workflows

Phase 1.5 additions:
- Tone presets and constraint injection
- Bulk regeneration helper
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Literal

RegenerationTarget = Literal[
    "factions",
    "locations",
    "npc_seeds",
    "opening",
    "threads",
]

REGENERATION_TARGETS: set[str] = {
    "factions",
    "locations",
    "npc_seeds",
    "opening",
    "threads",
}

# Phase 1.5 — Tone presets and default constraints
TONE_PRESETS: set[str] = {"neutral", "grim", "heroic", "chaotic"}

DEFAULT_CONSTRAINTS: dict[str, Any] = {
    "require_factions": False,
    "require_conflict": True,
    "npc_density": "medium",  # low / medium / high
}

RegenerationMode = Literal["preview", "apply"]

REGENERATION_MODES: set[str] = {"preview", "apply"}

ApplyStrategy = Literal["replace", "merge", "append"]

APPLY_STRATEGIES: set[str] = {"replace", "merge", "append"}

# Per-target strategy support matrix
TARGET_STRATEGIES: dict[str, set[str]] = {
    "factions": {"replace", "merge"},
    "locations": {"replace", "merge"},
    "npc_seeds": {"replace", "merge"},
    "opening": {"replace"},
    "threads": {"replace", "append"},
}

# Entity-type targets that support id-based merge and single-item regen
ENTITY_TARGETS: set[str] = {"factions", "locations", "npc_seeds"}

# Mapping from target to the id field used for merge
TARGET_ID_FIELD: dict[str, str] = {
    "factions": "faction_id",
    "locations": "location_id",
    "npc_seeds": "npc_id",
    "threads": "thread_id",
}


@dataclass
class RegenerationOptions:
    target: RegenerationTarget
    replace: bool = True
    preserve_ids: bool = True
    extra_context: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Apply-token generation
# ---------------------------------------------------------------------------


def generate_apply_token(target: str, payload_snapshot: Any = None) -> str:
    """Generate a lightweight apply token for a preview → apply handshake.

    The token encodes the target and a timestamp. It does **not** provide
    cryptographic guarantees — it is a UX-level contract for cleaner flows.
    """
    raw = f"regen_preview_{target}_{time.time()}"
    if payload_snapshot is not None:
        raw += f"_{id(payload_snapshot)}"
    return "regen_preview_" + hashlib.sha256(raw.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------


def _safe_list(value: Any) -> list[Any]:
    """Return *value* if it is a list, otherwise ``[]``."""
    return value if isinstance(value, list) else []


def _entity_id(item: Any, id_field: str) -> str | None:
    """Extract entity id from a dict or return None."""
    if isinstance(item, dict):
        return item.get(id_field)
    return None


def compute_section_diff(
    target: str,
    before: Any,
    after: Any,
    id_field: str | None = None,
) -> dict[str, Any]:
    """Compute a human-readable diff summary between two section snapshots.

    For entity targets (factions, locations, npc_seeds), performs id-based
    comparison. For opening/threads, does a simpler structural diff.

    Returns a dict with ``added``, ``removed``, ``changed``, and ``summary``.
    """
    if target in ENTITY_TARGETS:
        return _compute_entity_diff(target, before, after, id_field)
    if target == "threads":
        return _compute_thread_diff(before, after)
    if target == "opening":
        return _compute_opening_diff(before, after)
    return {"added": 0, "removed": 0, "changed": 0, "summary": []}


def _compute_entity_diff(
    target: str,
    before: Any,
    after: Any,
    id_field: str | None = None,
) -> dict[str, Any]:
    """Diff two entity lists by id field."""
    if id_field is None:
        id_field = TARGET_ID_FIELD.get(target, "id")
    before_list = [normalize_entity(item or {}) for item in _safe_list(before)]
    after_list = [normalize_entity(item or {}) for item in _safe_list(after)]

    before_ids = {_entity_id(e, id_field) for e in before_list if _entity_id(e, id_field)}
    after_ids = {_entity_id(e, id_field) for e in after_list if _entity_id(e, id_field)}

    added_ids = after_ids - before_ids
    removed_ids = before_ids - after_ids
    common_ids = before_ids & after_ids

    # Detect changed entities (same id, different content)
    before_map = {_entity_id(e, id_field): e for e in before_list if isinstance(e, dict)}
    after_map = {_entity_id(e, id_field): e for e in after_list if isinstance(e, dict)}

    changed = 0
    for eid in common_ids:
        if before_map.get(eid) != after_map.get(eid):
            changed += 1

    # Human-readable target labels
    label_map = {
        "factions": "faction",
        "locations": "location",
        "npc_seeds": "NPC",
    }
    label = label_map.get(target, "item")
    plural = label + "s"

    summary: list[str] = []
    if removed_ids:
        summary.append(f"{len(removed_ids)} {plural if len(removed_ids) != 1 else label} would be removed")
    if added_ids:
        summary.append(f"{len(added_ids)} new {plural if len(added_ids) != 1 else label} would be added")
    if changed:
        summary.append(f"{changed} {plural if changed != 1 else label} would change")

    return {
        "added": len(added_ids),
        "removed": len(removed_ids),
        "changed": changed,
        "summary": summary,
    }


def _compute_thread_diff(
    before: Any,
    after: Any,
) -> dict[str, Any]:
    """Diff two thread lists."""
    before_list = _safe_list(before)
    after_list = _safe_list(after)

    before_ids = {_entity_id(t, "thread_id") for t in before_list if _entity_id(t, "thread_id")}
    after_ids = {_entity_id(t, "thread_id") for t in after_list if _entity_id(t, "thread_id")}

    added = len(after_ids - before_ids)
    removed = len(before_ids - after_ids)

    summary: list[str] = []
    if removed:
        summary.append(f"{removed} thread{'s' if removed != 1 else ''} would be removed")
    if added:
        summary.append(f"{added} new thread{'s' if added != 1 else ''} would be added")

    return {"added": added, "removed": removed, "changed": 0, "summary": summary}


def _compute_opening_diff(
    before: Any,
    after: Any,
) -> dict[str, Any]:
    """Diff two opening snapshots."""
    before_dict = before if isinstance(before, dict) else {}
    after_dict = after if isinstance(after, dict) else {}

    changed_fields: list[str] = []
    all_keys = set(list(before_dict.keys()) + list(after_dict.keys()))
    for key in sorted(all_keys):
        if before_dict.get(key) != after_dict.get(key):
            changed_fields.append(key)

    summary: list[str] = []
    if changed_fields:
        summary.append(f"Opening would change: {', '.join(changed_fields)}")

    return {
        "added": 0,
        "removed": 0,
        "changed": len(changed_fields),
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Single-item diff
# ---------------------------------------------------------------------------


def _normalize_scalar(value: Any) -> Any:
    """Normalize a scalar value for diff comparison."""
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return value.strip()
    return value


def normalize_entity(entity: dict[str, Any]) -> dict[str, Any]:
    """Normalize entities before diffing to avoid false positives."""
    normalized: dict[str, Any] = {}
    for key in sorted(entity.keys()):
        value = entity[key]
        if isinstance(value, list):
            cleaned = [_normalize_scalar(v) for v in value]
            cleaned = [v for v in cleaned if v not in (None, [], {})]
            if cleaned:
                normalized[key] = cleaned
        elif isinstance(value, dict):
            nested = {
                k: _normalize_scalar(v)
                for k, v in sorted(value.items())
                if _normalize_scalar(v) not in (None, [], {})
            }
            if nested:
                normalized[key] = nested
        else:
            cleaned = _normalize_scalar(value)
            if cleaned is not None:
                normalized[key] = cleaned
    return normalized


def compute_item_diff(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Compute a field-level diff between two entity dicts.

    Returns a dict with ``changed_fields`` listing which keys differ.
    """
    before = normalize_entity(before or {})
    after = normalize_entity(after or {})

    all_keys = set(list(before.keys()) + list(after.keys()))
    changed: list[str] = []
    for key in sorted(all_keys):
        if before.get(key) != after.get(key):
            changed.append(key)

    return {"changed_fields": changed}


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------


def merge_entity_lists(
    current: list[dict[str, Any]],
    regenerated: list[dict[str, Any]],
    id_field: str,
) -> list[dict[str, Any]]:
    """Merge regenerated entities into current list by id field.

    Rules:
    - If a regenerated entity's id already exists, overwrite that entity.
    - If a regenerated entity's id is new, append it.
    - Keep current entities not mentioned by regeneration.
    - Raises ValueError if regenerated item is missing required id field.
    """
    merged: dict[str, dict[str, Any]] = {}

    for item in current or []:
        item_id = item.get(id_field)
        if not item_id:
            continue
        merged[item_id] = dict(item)

    for item in regenerated or []:
        item_id = item.get(id_field)
        if not item_id:
            raise ValueError(f"Missing id field '{id_field}' in regenerated entity")
        merged[item_id] = dict(item)

    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item_id, item in merged.items():
        if item_id in seen:
            continue
        seen.add(item_id)
        result.append(item)
    return result


def merge_thread_lists(
    current: list[dict[str, Any]],
    regenerated: list[dict[str, Any]],
    strategy: str = "append",
) -> list[dict[str, Any]]:
    """Merge regenerated threads into current list.

    ``strategy='merge'``: id-based merge (same as entities).
    ``strategy='append'``: append all regenerated threads.
    """
    current_list = _safe_list(current)
    regen_list = _safe_list(regenerated)

    if strategy == "merge":
        return merge_entity_lists(current_list, regen_list, "thread_id")

    # Append: add all regenerated threads, dedup by thread_id
    existing_ids = {
        t.get("thread_id")
        for t in current_list
        if isinstance(t, dict) and t.get("thread_id")
    }
    result = list(current_list)
    for item in regen_list:
        if isinstance(item, dict):
            tid = item.get("thread_id")
            if tid and tid not in existing_ids:
                result.append(item)
                existing_ids.add(tid)
    return result


# ---------------------------------------------------------------------------
# Phase 1.5 — Constraint & tone injection helpers
# ---------------------------------------------------------------------------


def apply_constraints_to_setup(setup: dict[str, Any], constraints: dict[str, Any] | None) -> dict[str, Any]:
    """Lightweight constraint injector (Phase 1.5)."""
    setup = dict(setup or {})
    meta = dict(setup.get("metadata") or {})
    meta["constraints"] = constraints or {}
    setup["metadata"] = meta
    return setup


def apply_tone_to_setup(setup: dict[str, Any], tone: str | None) -> dict[str, Any]:
    """Inject tone preset into setup metadata (Phase 1.5)."""
    if not tone:
        return setup
    if tone not in TONE_PRESETS:
        return setup
    setup = dict(setup or {})
    meta = dict(setup.get("metadata") or {})
    meta["tone"] = tone
    setup["metadata"] = meta
    return setup


# ---------------------------------------------------------------------------
# Phase 1.5 — Bulk regeneration helper
# ---------------------------------------------------------------------------


def regenerate_multiple_items(
    setup: dict[str, Any],
    target: str,
    item_ids: list[str],
    regenerate_fn: Any,
) -> list[dict[str, Any]]:
    """Regenerate multiple entities safely.

    Note: exceptions during individual item regeneration are silently
    skipped to allow partial success — the caller decides how to handle
    incomplete results.
    """
    results: list[dict[str, Any]] = []
    for item_id in item_ids:
        try:
            result = regenerate_fn(setup, target, item_id)
            if result:
                results.append(result)
        except Exception:  # noqa: BLE001 — intentional: partial success over total failure
            continue
    return results


def build_regeneration_rationale(target: str, setup: dict[str, Any], regenerated: Any) -> str:
    """Build a human-readable rationale for a regeneration operation."""
    if target == "factions":
        count = len(regenerated or [])
        return f"Generated {count} factions aligned with the current premise, setting, and tone."
    if target == "locations":
        count = len(regenerated or [])
        return f"Generated {count} locations aligned with the world setup and starting context."
    if target == "npc_seeds":
        count = len(regenerated or [])
        return f"Generated {count} NPCs aligned with the current factions, locations, and premise."
    if target == "opening":
        return "Regenerated the opening to better match the current setup and resolved starting context."
    if target == "threads":
        count = len(regenerated or [])
        return f"Generated {count} tensions/threads to increase early pressure and tie into the premise."
    return "Regenerated content using the current creator setup."
