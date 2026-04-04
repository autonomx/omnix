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
from ..creator.schema import AdventureSetup
from ..creator.validation import validate_adventure_setup_payload
from .adventure_response_adapter import adapt_start_result


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
    raw = build_setup_template(template_name)
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
    from ..creator.presenters import CreatorStatePresenter

    data = apply_adventure_defaults(dict(payload))
    validation = validate_adventure_setup_payload(data)

    if validation.is_blocking():
        return {
            "success": True,
            "ok": False,
            "validation": validation.to_dict(),
        }

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

    return {
        "success": True,
        "ok": True,
        "validation": validation.to_dict(),
        "preview": preview,
        "resolved_context": resolved_context,
    }


# ---------------------------------------------------------------------------
# Start adventure
# ---------------------------------------------------------------------------


def start_adventure(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a brand-new adventure using the structured creator pipeline.

    Instantiates a minimal ``GameLoop`` (with stubbed subsystems), runs
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

    # Build a GameLoop with stubbed subsystems (no live LLM required at
    # startup — the pipeline is deterministic).
    loop = GameLoop(
        intent_parser=_stub(),
        world=_stub(),
        npc_system=_stub(),
        event_bus=_stub(),
        story_director=_stub(),
        scene_renderer=_stub(),
    )

    result = loop.start_new_adventure(data)

    if not result.get("ok"):
        return {"success": False, "error": "Adventure start failed", "details": result}

    adapted = adapt_start_result(result)
    return adapted


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _Stub:
    """Minimal stub that absorbs any attribute access / method call."""

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        return _Stub()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return None

    def __bool__(self) -> bool:
        return False


def _stub() -> _Stub:
    return _Stub()
