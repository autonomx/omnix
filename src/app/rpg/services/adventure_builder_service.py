"""High-level service that orchestrates the creator / adventure-builder flow.

Wraps the ``AdventureSetup`` schema, ``creator.defaults``, ``creator.validation``,
and ``GameLoop.prepare_new_adventure()`` / ``start_new_adventure()`` behind a
simple method interface consumed by the creator routes.
"""

from __future__ import annotations

import uuid
from typing import Any

from ..creator.defaults import (
    apply_adventure_defaults,
    build_setup_template,
    list_setup_templates,
)
from ..creator.regeneration import REGENERATION_TARGETS
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


def _apply_regenerated_section(
    setup_payload: dict[str, Any],
    target: str,
    regenerated: Any,
) -> dict[str, Any]:
    """Merge a regenerated section back into the setup payload.

    Parameters
    ----------
    setup_payload :
        The current (normalized) setup dict.
    target :
        One of ``REGENERATION_TARGETS`` (``"factions"``, ``"locations"``,
        ``"npc_seeds"``, ``"opening"``, ``"threads"``).
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
        # Stored in metadata for preview-time use until formal setup field exists.
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


def regenerate_setup_section(payload: dict[str, Any], target: str) -> dict[str, Any]:
    """Regenerate a single section of an adventure setup.

    Parameters
    ----------
    payload :
        Raw setup dict (may be incomplete — defaults are applied).
    target :
        One of ``REGENERATION_TARGETS``.

    Returns
    -------
    dict
        Response dict with ``success``, ``target``, ``updated_setup``,
        ``regenerated``, ``validation``, ``preview``, and ``resolved_context``.
    """
    if target not in REGENERATION_TARGETS:
        return {
            "success": False,
            "error": f"Unsupported regeneration target: {target}",
        }

    normalized_payload = apply_adventure_defaults(dict(payload or {}))
    validation = validate_adventure_setup_payload(normalized_payload)

    # Allow regeneration even with warnings, but block on hard-invalid payloads.
    if validation.is_blocking():
        return {
            "success": False,
            "error": "Setup has blocking validation issues",
            "validation": validation.to_dict(),
        }

    # Build the startup pipeline directly — we don't need a full GameLoop for regeneration.
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
        regenerated = pipeline.regenerate_factions(setup)
    elif target == "locations":
        regenerated = pipeline.regenerate_locations(setup)
    elif target == "npc_seeds":
        regenerated = pipeline.regenerate_npc_seeds(setup)
    elif target == "threads":
        regenerated = pipeline.regenerate_threads(setup)
    elif target == "opening":
        regenerated = pipeline.regenerate_opening(setup)
    else:
        raise ValueError(f"Unsupported regeneration target: {target}")

    next_payload = _apply_regenerated_section(normalized_payload, target, regenerated)
    prepared = _build_preview_contract_from_payload(next_payload)

    return {
        "success": True,
        "target": target,
        "updated_setup": next_payload,
        "regenerated": regenerated,
        "validation": prepared.get("validation"),
        "preview": prepared.get("preview"),
        "resolved_context": prepared.get("resolved_context"),
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
