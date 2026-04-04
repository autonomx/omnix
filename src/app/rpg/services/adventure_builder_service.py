"""High-level service that orchestrates the creator / adventure-builder flow.

Wraps the ``AdventureSetup`` schema, ``creator.defaults``, ``creator.validation``,
and ``GameLoop.prepare_new_adventure()`` / ``start_new_adventure()`` behind a
simple method interface consumed by the creator routes.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from ..creator.defaults import (
    apply_adventure_defaults,
    build_setup_template,
    list_setup_templates,
)
from ..creator.regeneration import (
    APPLY_STRATEGIES,
    ENTITY_TARGETS,
    REGENERATION_MODES,
    REGENERATION_TARGETS,
    TARGET_ID_FIELD,
    TARGET_STRATEGIES,
    apply_constraints_to_setup,
    apply_tone_to_setup,
    build_regeneration_rationale,
    compute_item_diff,
    compute_section_diff,
    generate_apply_token,
    merge_entity_lists,
    merge_thread_lists,
)
from ..creator.schema import AdventureSetup
from ..creator.validation import validate_adventure_setup_payload
from .adventure_response_adapter import ADVENTURE_START_RESPONSE_VERSION, adapt_start_result

# ---------------------------------------------------------------------------
# Response version constants — bump when the contract changes
# ---------------------------------------------------------------------------

ADVENTURE_PREVIEW_RESPONSE_VERSION = 1


# ---------------------------------------------------------------------------
# Preview response builder — stabilises the contract for the frontend
# ---------------------------------------------------------------------------


def _safe_list(value: Any) -> list[Any]:
    """Return *value* if it is already a list, otherwise ``[]``."""
    if isinstance(value, list):
        return value
    return []


def _safe_dict(value: Any) -> dict[str, Any]:
    """Return *value* if it is already a dict, otherwise ``{}``."""
    if isinstance(value, dict):
        return value
    return {}


def _build_preview_contract(prepared: dict[str, Any]) -> dict[str, Any]:
    """Convert the internal ``GameLoop.prepare_new_adventure()`` output to a
    deterministic preview response shape.

    Parameters
    ----------
    prepared:
        The dict returned by ``GameLoop.prepare_new_adventure()``.
        Expected keys: ``ok``, ``validation``, ``preview``, ``resolved_context``.

    Returns
    -------
    dict
        Frontend-friendly payload with ``response_version``, ``success``,
        ``ok``, ``validation``, ``preview``, and ``resolved_context``.
    """
    validation = _safe_dict(prepared.get("validation"))
    preview = _safe_dict(prepared.get("preview"))
    resolved_context = _safe_dict(prepared.get("resolved_context"))

    counts = _safe_dict(preview.get("counts"))
    warnings = _safe_list(preview.get("warnings"))

    return {
        "success": True,
        "response_version": ADVENTURE_PREVIEW_RESPONSE_VERSION,
        "ok": bool(prepared.get("ok")),
        "validation": {
            "issues": _safe_list(validation.get("issues")),
            "blocking": bool(validation.get("blocking")),
            "hints": _safe_list(validation.get("hints")),
        },
        "preview": {
            "title": preview.get("title") or "",
            "genre": preview.get("genre") or "",
            "setting": preview.get("setting") or "",
            "premise": preview.get("premise") or "",
            "counts": {
                "factions": counts.get("factions", 0),
                "locations": counts.get("locations", 0),
                "npcs": counts.get("npcs", 0),
            },
            "warnings": warnings,
        },
        "resolved_context": {
            "location_id": resolved_context.get("location_id"),
            "location_name": resolved_context.get("location_name") or "",
            "npc_ids": _safe_list(resolved_context.get("npc_ids")),
            "npc_names": _safe_list(resolved_context.get("npc_names")),
        },
    }


# ---------------------------------------------------------------------------
# Template listing / building
# ---------------------------------------------------------------------------


def get_templates() -> list[dict[str, Any]]:
    """Return available adventure setup templates with metadata."""
    return list_setup_templates()


def build_template_payload(template_name: str) -> dict[str, Any]:
    """Build a full editable setup dict from a named template.

    Applies canonical defaults after template hydration so the caller
    receives a complete payload ready for UI editing.
    """
    try:
        raw = build_setup_template(template_name)
    except ValueError:
        return {"success": False, "error": f"Unknown template: {template_name}"}
    if raw is None:
        return {"success": False, "error": f"Unknown template: {template_name}"}
    payload = apply_adventure_defaults(dict(raw))
    return {"success": True, "setup": payload}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_setup(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate an adventure setup payload.

    Returns the validation result dict with ``issues`` and ``blocking``.
    """
    result = validate_adventure_setup_payload(payload)
    return {"success": True, "validation": result.to_dict()}


# ---------------------------------------------------------------------------
# Preview (normalize + defaults + validation + summary)
# ---------------------------------------------------------------------------


def preview_setup(payload: dict[str, Any]) -> dict[str, Any]:
    """Prepare a rich preview of the adventure setup.

    Normalizes → applies defaults → validates → builds a presenter summary,
    then resolves the starting context so the frontend can show "Opening in:
    <location>, Present: <actors>".
    """
    from ..core.game_loop import GameLoop
    from ..creator.presenters import CreatorStatePresenter

    data = apply_adventure_defaults(dict(payload))
    validation = validate_adventure_setup_payload(data)

    if validation.is_blocking():
        return _build_preview_contract({
            "ok": False,
            "validation": validation.to_dict(),
            "preview": {},
            "resolved_context": {},
        })

    setup = AdventureSetup.from_dict(data).normalize().with_defaults()
    presenter = CreatorStatePresenter()
    preview = presenter.present_setup_summary(setup)

    # Resolve starting context locally (mirrors StartupGenerationPipeline)
    location_id = setup.starting_location_id
    if not location_id and setup.locations:
        location_id = setup.locations[0].location_id

    npc_ids = list(setup.starting_npc_ids)
    if not npc_ids and setup.npc_seeds:
        npc_ids = [npc.npc_id for npc in setup.npc_seeds[:3]]

    # Human-readable names for resolved context
    location_name = location_id or ""
    for loc in setup.locations:
        if loc.location_id == location_id:
            location_name = loc.name
            break

    npc_names: list[str] = []
    npc_lookup = {npc.npc_id: npc.name for npc in setup.npc_seeds}
    for npc_id in npc_ids:
        npc_names.append(npc_lookup.get(npc_id, npc_id))

    resolved_context = {
        "location_id": location_id,
        "location_name": location_name,
        "npc_ids": npc_ids,
        "npc_names": npc_names,
    }

    counts = {
        "factions": len(setup.factions),
        "locations": len(setup.locations),
        "npcs": len(setup.npc_seeds),
    }

    prepared = {
        "ok": True,
        "validation": validation.to_dict(),
        "preview": {
            "title": setup.title,
            "genre": setup.genre,
            "setting": setup.setting,
            "premise": setup.premise,
            "counts": counts,
            "warnings": [],
        },
        "resolved_context": resolved_context,
    }

    return _build_preview_contract(prepared)


# ---------------------------------------------------------------------------
# Start adventure
# ---------------------------------------------------------------------------


def start_adventure(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a brand-new adventure using the structured creator pipeline.

    Instantiates a minimal ``GameLoop`` (with explicit null dependencies), runs
    ``start_new_adventure()``, then adapts the result into the session shape
    expected by the frontend.
    """
    from ..core.game_loop import GameLoop

    data = apply_adventure_defaults(dict(payload))

    # Ensure a setup_id exists
    if not data.get("setup_id"):
        data["setup_id"] = f"adventure_{uuid.uuid4().hex[:12]}"

    # Pre-validate before spinning up the loop
    validation = validate_adventure_setup_payload(data)
    if validation.is_blocking():
        return {
            "success": False,
            "error": "Setup has blocking validation issues",
            "validation": validation.to_dict(),
        }

    # Build a GameLoop with explicit null dependencies — fail-fast if creator
    # flows touch unexpected collaborators.
    loop = _build_game_loop()

    result = loop.start_new_adventure(data)

    if not result.get("ok"):
        return {"success": False, "error": "Adventure start failed", "details": result}

    adapted = adapt_start_result(result)
    adapted["preview_response_version"] = ADVENTURE_PREVIEW_RESPONSE_VERSION
    adapted["start_response_version"] = ADVENTURE_START_RESPONSE_VERSION
    return adapted


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _NullDependency:
    """Intentional null object used only for non-essential GameLoop collaborators.

    This class is deliberately narrow. It should not silently absorb arbitrary
    attribute chains, because that can hide integration regressions.
    """

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        raise AttributeError(
            f"Unexpected access to null dependency attribute: {name}"
        )


def _build_game_loop() -> "GameLoop":
    """Construct a GameLoop instance for creator preview/start flows.

    Uses minimal mock/stub dependencies since the regeneration pipeline
    only needs access to the startup_generation_pipeline, not full execution.
    """
    from ..core.event_bus import EventBus
    from ..core.game_loop import GameLoop

    # Create a real EventBus — other deps can be null objects for creator flows.
    event_bus = EventBus()
    return GameLoop(
        intent_parser=_NullDependency(),
        world=_NullDependency(),
        npc_system=_NullDependency(),
        event_bus=event_bus,
        story_director=_NullDependency(),
        scene_renderer=_NullDependency(),
    )


def _bootstrap_loop_dependencies() -> None:
    """Ensure all GameLoop subclasses are importable and initialized.

    This is a no-op helper kept for compatibility — the real initialization
    happens inside _build_game_loop().
    """
    pass


# ---------------------------------------------------------------------------
# Targeted regeneration helpers
# ---------------------------------------------------------------------------


def _replace_regenerated_section(
    setup_payload: dict[str, Any],
    target: str,
    regenerated: Any,
) -> dict[str, Any]:
    """Replace a section entirely (Phase 1.3 behaviour).

    Parameters
    ----------
    setup_payload :
        The current (normalized) setup dict.
    target :
        One of ``REGENERATION_TARGETS``.
    regenerated :
        The data returned by the startup pipeline's regenerate_* method.

    Returns
    -------
    dict
        A new setup payload with the requested section replaced.
    """
    next_payload = dict(setup_payload)

    if target == "factions":
        next_payload["factions"] = list(regenerated or [])
    elif target == "locations":
        next_payload["locations"] = list(regenerated or [])
    elif target == "npc_seeds":
        next_payload["npc_seeds"] = list(regenerated or [])
    elif target == "threads":
        metadata = dict(next_payload.get("metadata") or {})
        metadata["regenerated_threads"] = list(regenerated or [])
        next_payload["metadata"] = metadata
    elif target == "opening":
        metadata = dict(next_payload.get("metadata") or {})
        metadata["regenerated_opening"] = dict(regenerated or {})
        next_payload["metadata"] = metadata
        resolved = (regenerated or {}).get("resolved_context") or {}
        if resolved.get("location_id"):
            next_payload["starting_location_id"] = resolved["location_id"]
        if resolved.get("npc_ids"):
            next_payload["starting_npc_ids"] = list(resolved["npc_ids"])
    else:
        raise ValueError(f"Unsupported regeneration target: {target}")

    return next_payload


def _merge_regenerated_section(
    setup_payload: dict[str, Any],
    target: str,
    regenerated: Any,
) -> dict[str, Any]:
    """Merge regenerated data into the existing section by stable id.

    Parameters
    ----------
    setup_payload :
        The current (normalized) setup dict.
    target :
        One of ``REGENERATION_TARGETS`` that supports merge.
    regenerated :
        The regenerated data.

    Returns
    -------
    dict
        A new setup payload with the section merged.
    """
    next_payload = dict(setup_payload)
    id_field = TARGET_ID_FIELD.get(target, "id")

    if target in ENTITY_TARGETS:
        current = list(next_payload.get(target) or [])
        regen_list = list(regenerated or [])
        next_payload[target] = merge_entity_lists(current, regen_list, id_field)
    elif target == "threads":
        metadata = dict(next_payload.get("metadata") or {})
        current_threads = list(metadata.get("regenerated_threads") or [])
        regen_threads = list(regenerated or [])
        metadata["regenerated_threads"] = merge_thread_lists(
            current_threads, regen_threads, strategy="append"
        )
        next_payload["metadata"] = metadata
    else:
        # Fallback to replace for targets that don't support merge
        return _replace_regenerated_section(setup_payload, target, regenerated)

    return next_payload


def _apply_regenerated_section(
    setup_payload: dict[str, Any],
    target: str,
    regenerated: Any,
    strategy: str = "replace",
) -> dict[str, Any]:
    """Apply a regenerated section to the setup payload, dispatching by strategy.

    Parameters
    ----------
    setup_payload :
        The current (normalized) setup dict.
    target :
        One of ``REGENERATION_TARGETS``.
    regenerated :
        The data returned by the startup pipeline's regenerate_* method.
    strategy :
        One of ``"replace"``, ``"merge"``, ``"append"``.

    Returns
    -------
    dict
        A new setup payload with the requested section updated.
    """
    if strategy == "merge":
        return _merge_regenerated_section(setup_payload, target, regenerated)
    if strategy == "append" and target == "threads":
        return _merge_regenerated_section(setup_payload, target, regenerated)
    return _replace_regenerated_section(setup_payload, target, regenerated)


# ---------------------------------------------------------------------------
# In-memory preview store (keyed by apply_token)
# ---------------------------------------------------------------------------

_preview_store: dict[str, dict[str, Any]] = {}
_PREVIEW_TTL_SEC = 300
_MAX_PREVIEWS = 100


def _cleanup_preview_store(now: float | None = None) -> None:
    """Remove expired previews and enforce max size limit."""
    ts = now or time.time()
    expired = [
        token
        for token, payload in _preview_store.items()
        if (ts - float(payload.get("created_at", 0))) > _PREVIEW_TTL_SEC
    ]
    for token in expired:
        _preview_store.pop(token, None)

    if len(_preview_store) > _MAX_PREVIEWS:
        ordered = sorted(
            _preview_store.items(),
            key=lambda kv: float(kv[1].get("created_at", 0)),
        )
        for token, _ in ordered[: max(0, len(_preview_store) - _MAX_PREVIEWS)]:
            _preview_store.pop(token, None)


def _store_preview(token: str, data: dict[str, Any]) -> None:
    """Store a preview result keyed by token. Evicts expired/oldest if limit reached."""
    _cleanup_preview_store()
    entry = dict(data)
    entry["created_at"] = time.time()
    _preview_store[token] = entry


def _pop_preview(token: str) -> dict[str, Any] | None:
    """Retrieve and remove a stored preview by token."""
    _cleanup_preview_store()
    return _preview_store.pop(token, None)


# ---------------------------------------------------------------------------
# Section-level regeneration (Phase 1.4A)
# ---------------------------------------------------------------------------


def _get_current_section(payload: dict[str, Any], target: str) -> Any:
    """Extract the current section data from a setup payload for diff."""
    if target in ENTITY_TARGETS:
        return list(payload.get(target) or [])
    if target == "threads":
        metadata = payload.get("metadata") or {}
        return list(metadata.get("regenerated_threads") or [])
    if target == "opening":
        metadata = payload.get("metadata") or {}
        return dict(metadata.get("regenerated_opening") or {})
    return None


def _run_regeneration(normalized_payload: dict[str, Any], target: str) -> Any:
    """Run the startup pipeline regeneration for a given target.

    Returns the regenerated data.
    """
    from ..core.event_bus import EventBus
    from ..creator.canon import CreatorCanonState
    from ..creator.startup_pipeline import StartupGenerationPipeline

    event_bus = EventBus()
    canon_state = CreatorCanonState()
    pipeline = StartupGenerationPipeline(
        llm_gateway=_NullDependency(),
        coherence_core=event_bus,
        creator_canon_state=canon_state,
    )
    setup = AdventureSetup.from_dict(normalized_payload).normalize().with_defaults()

    if target == "factions":
        return pipeline.regenerate_factions(setup)
    elif target == "locations":
        return pipeline.regenerate_locations(setup)
    elif target == "npc_seeds":
        return pipeline.regenerate_npc_seeds(setup)
    elif target == "threads":
        return pipeline.regenerate_threads(setup)
    elif target == "opening":
        return pipeline.regenerate_opening(setup)
    else:
        raise ValueError(f"Unsupported regeneration target: {target}")


def regenerate_setup_section(
    payload: dict[str, Any],
    target: str,
    mode: str = "apply",
    apply_token: str | None = None,
    apply_strategy: str = "replace",
    tone: str | None = None,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Regenerate a single section of an adventure setup.

    Parameters
    ----------
    payload :
        Raw setup dict (may be incomplete — defaults are applied).
    target :
        One of ``REGENERATION_TARGETS``.
    mode :
        ``"preview"`` to get a diff without applying, or ``"apply"`` to apply.
    apply_token :
        Optional token from a previous preview to apply cached results.
    apply_strategy :
        One of ``"replace"``, ``"merge"``, ``"append"``.
    tone :
        Optional tone preset (Phase 1.5).
    constraints :
        Optional constraint dict (Phase 1.5).

    Returns
    -------
    dict
        Response dict whose shape varies by mode.
    """
    if target not in REGENERATION_TARGETS:
        return {
            "success": False,
            "error": f"Unsupported regeneration target: {target}",
        }

    if mode and mode not in REGENERATION_MODES:
        return {
            "success": False,
            "error": f"Unsupported regeneration mode: {mode}",
        }

    # Validate strategy against target
    allowed = TARGET_STRATEGIES.get(target, {"replace"})
    effective_strategy = apply_strategy if apply_strategy in allowed else "replace"

    normalized_payload = apply_adventure_defaults(dict(payload or {}))

    # Phase 1.5 — inject constraints and tone before generation
    normalized_payload = apply_constraints_to_setup(normalized_payload, constraints)
    normalized_payload = apply_tone_to_setup(normalized_payload, tone)

    validation = validate_adventure_setup_payload(normalized_payload)

    if validation.is_blocking():
        return {
            "success": False,
            "error": "Setup has blocking validation issues",
            "validation": validation.to_dict(),
        }

    # ── Preview mode ────────────────────────────────────────────────────
    if mode == "preview":
        before = _get_current_section(normalized_payload, target)
        regenerated = _run_regeneration(normalized_payload, target)
        after = regenerated

        diff = compute_section_diff(target, before, after)
        token = generate_apply_token(target, normalized_payload)

        # Store preview for later apply
        _store_preview(token, {
            "target": target,
            "setup_id": normalized_payload.get("setup_id"),
            "before": before,
            "after": regenerated,
            "apply_strategy": apply_strategy,
        })

        return {
            "success": True,
            "target": target,
            "mode": "preview",
            "before": before,
            "after": regenerated,
            "diff": diff,
            "summary": diff.get("summary", []),
            "rationale": build_regeneration_rationale(target, normalized_payload, regenerated),
            "apply_token": token,
        }

    # ── Apply mode ──────────────────────────────────────────────────────
    # Strict apply_token validation
    preview = _pop_preview(apply_token)
    if not preview:
        return {"success": False, "error": "Invalid or expired apply_token"}
    if preview.get("target") != target:
        return {"success": False, "error": "Mismatched regeneration target"}
    if preview.get("setup_id") != normalized_payload.get("setup_id"):
        return {"success": False, "error": "Mismatched setup for apply_token"}

    regenerated = preview.get("after")

    next_payload = _apply_regenerated_section(
        normalized_payload, target, regenerated, strategy=effective_strategy,
    )
    prepared = _build_preview_contract_from_payload(next_payload)

    return {
        "success": True,
        "target": target,
        "mode": "apply",
        "updated_setup": next_payload,
        "regenerated": regenerated,
        "validation": prepared.get("validation"),
        "preview": prepared.get("preview"),
        "resolved_context": prepared.get("resolved_context"),
        "rationale": build_regeneration_rationale(target, normalized_payload, regenerated),
        "health": compute_creator_health(next_payload),
    }


# ---------------------------------------------------------------------------
# Single-item regeneration (Phase 1.4C)
# ---------------------------------------------------------------------------


def regenerate_single_item(
    payload: dict[str, Any],
    target: str,
    item_id: str,
) -> dict[str, Any]:
    """Regenerate a single entity within a section.

    Parameters
    ----------
    payload :
        Raw setup dict.
    target :
        One of the entity targets (``"factions"``, ``"locations"``, ``"npc_seeds"``).
    item_id :
        The id of the entity to regenerate.

    Returns
    -------
    dict
        Response with ``before``, ``after``, ``diff``, and ``updated_setup``.
    """
    if target not in ENTITY_TARGETS:
        return {
            "success": False,
            "error": f"Single-item regeneration is only supported for: {', '.join(sorted(ENTITY_TARGETS))}",
        }

    id_field = TARGET_ID_FIELD.get(target, "id")

    normalized_payload = apply_adventure_defaults(dict(payload or {}))
    validation = validate_adventure_setup_payload(normalized_payload)

    if validation.is_blocking():
        return {
            "success": False,
            "error": "Setup has blocking validation issues",
            "validation": validation.to_dict(),
        }

    # Find the current entity
    current_list = list(normalized_payload.get(target) or [])
    before_item = None
    before_idx = None
    for idx, item in enumerate(current_list):
        if isinstance(item, dict) and item.get(id_field) == item_id:
            before_item = dict(item)
            before_idx = idx
            break

    if before_item is None:
        return {
            "success": False,
            "error": f"Item '{item_id}' not found in {target}",
        }

    # Regenerate the whole section, then extract the matching item
    regenerated_section = _run_regeneration(normalized_payload, target)
    regen_list = list(regenerated_section or [])

    # Try to find the item with the same id in the regenerated output
    after_item = None
    for item in regen_list:
        if isinstance(item, dict) and item.get(id_field) == item_id:
            after_item = dict(item)
            break

    if after_item is None:
        # Regenerated section doesn't have this id — generate a replacement
        # by taking any item from the regenerated set with the same index
        if before_idx is not None and before_idx < len(regen_list):
            after_item = dict(regen_list[before_idx])
        elif regen_list:
            after_item = dict(regen_list[0])
        else:
            after_item = dict(before_item)

        # Preserve the original id and name
        after_item[id_field] = item_id
        if "name" in before_item:
            after_item["name"] = before_item["name"]

    diff = compute_item_diff(before_item, after_item)

    # Build updated_setup with the single item replaced
    updated_list = list(current_list)
    if before_idx is not None:
        updated_list[before_idx] = after_item
    next_payload = dict(normalized_payload)
    next_payload[target] = updated_list

    prepared = _build_preview_contract_from_payload(next_payload)

    return {
        "success": True,
        "target": target,
        "item_id": item_id,
        "before": before_item,
        "after": after_item,
        "diff": diff,
        "updated_setup": next_payload,
        "validation": prepared.get("validation"),
        "preview": prepared.get("preview"),
        "resolved_context": prepared.get("resolved_context"),
        "rationale": build_regeneration_rationale(target, normalized_payload, [after_item]),
        "health": compute_creator_health(next_payload),
    }


def _build_preview_contract_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a preview contract from a setup payload (without validation).

    Re-generates the resolved_context and preview summary for the given payload.
    """
    setup = AdventureSetup.from_dict(payload).normalize().with_defaults()

    # Resolve starting context locally (mirrors StartupGenerationPipeline)
    location_id = setup.starting_location_id
    if not location_id and setup.locations:
        location_id = setup.locations[0].location_id

    npc_ids = list(setup.starting_npc_ids)
    if not npc_ids and setup.npc_seeds:
        npc_ids = [npc.npc_id for npc in setup.npc_seeds[:3]]

    # Human-readable names for resolved context
    location_name = location_id or ""
    for loc in setup.locations:
        if loc.location_id == location_id:
            location_name = loc.name
            break

    npc_names: list[str] = []
    npc_lookup = {npc.npc_id: npc.name for npc in setup.npc_seeds}
    for npc_id in npc_ids:
        npc_names.append(npc_lookup.get(npc_id, npc_id))

    resolved_context = {
        "location_id": location_id,
        "location_name": location_name,
        "npc_ids": npc_ids,
        "npc_names": npc_names,
    }

    counts = {
        "factions": len(setup.factions),
        "locations": len(setup.locations),
        "npcs": len(setup.npc_seeds),
    }

    return {
        "ok": True,
        "validation": {"issues": [], "blocking": False, "hints": []},
        "preview": {
            "title": setup.title,
            "genre": setup.genre,
            "setting": setup.setting,
            "premise": setup.premise,
            "counts": counts,
            "warnings": [],
        },
        "resolved_context": resolved_context,
    }


# ---------------------------------------------------------------------------
# Phase 1.5 — Creator health warnings
# ---------------------------------------------------------------------------


def compute_creator_health(setup_payload: dict[str, Any]) -> dict[str, Any]:
    """Compute health warnings for the current setup (Phase 1.5).

    Returns a dict with ``warnings`` and a ``score`` (0-100).
    """
    warnings: list[str] = []

    if len(_safe_list(setup_payload.get("npc_seeds"))) < 2:
        warnings.append("Very few NPCs — consider adding more for richer interactions.")

    if len(_safe_list(setup_payload.get("factions"))) == 0:
        warnings.append("No factions defined — world may feel flat.")

    if not setup_payload.get("starting_location_id"):
        warnings.append("No starting location set.")

    return {
        "warnings": warnings,
        "score": max(0, 100 - (len(warnings) * 20)),
    }


# ---------------------------------------------------------------------------
# Phase 1.5 — Bulk regeneration service
# ---------------------------------------------------------------------------


def regenerate_multiple_items_service(
    payload: dict[str, Any],
    target: str,
    item_ids: list[str],
) -> dict[str, Any]:
    """Regenerate multiple entities within a section (Phase 1.5).

    Regenerations are applied sequentially — each item is regenerated against
    the setup produced by the previous item's regeneration, so results are
    cumulative rather than independent.

    Parameters
    ----------
    payload :
        Raw setup dict.
    target :
        One of the entity targets.
    item_ids :
        List of entity ids to regenerate.

    Returns
    -------
    dict
        Response with ``success``, ``target``, ``count``, and ``items``.
    """
    if not item_ids:
        return {"success": False, "error": "Missing item_ids"}

    results: list[dict[str, Any]] = []
    next_payload = dict(payload or {})

    for item_id in item_ids:
        res = regenerate_single_item(next_payload, target, item_id)
        if res.get("success"):
            results.append(res["after"])
            if res.get("updated_setup"):
                next_payload = res["updated_setup"]

    return {
        "success": True,
        "target": target,
        "count": len(results),
        "items": results,
        "updated_setup": next_payload,
        "health": compute_creator_health(next_payload),
    }
