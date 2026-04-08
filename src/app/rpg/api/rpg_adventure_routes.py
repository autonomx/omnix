"""Phase 90 — Adventure Builder API routes.

Provides endpoints for the adventure creation/editing flow:
- GET  /api/rpg/adventure/templates          — list available templates
- POST /api/rpg/adventure/template           — build a template payload
- POST /api/rpg/adventure/validate           — validate a setup payload
- POST /api/rpg/adventure/preview            — preview a setup
- POST /api/rpg/adventure/start              — start a new adventure
- POST /api/rpg/adventure/regenerate         — regenerate a section
- POST /api/rpg/adventure/regenerate-item    — regenerate a single item
- POST /api/rpg/adventure/regenerate-multiple — regenerate multiple items
- POST /api/rpg/adventure/inspect-world      — inspect the world graph
- POST /api/rpg/adventure/inspect-world-snapshot — build a world snapshot
- POST /api/rpg/adventure/compare-world      — compare two setups
- POST /api/rpg/adventure/compare-entity     — compare a single entity
- POST /api/rpg/adventure/simulate-step      — advance simulation by one tick
- POST /api/rpg/adventure/simulation-state   — get current simulation state
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..services.adventure_builder_service import (
    build_adventure_preview,
    build_template_payload,
    compare_world,
    compute_creator_health,
    get_templates,
    inspect_world,
    inspect_world_snapshot,
    preview_setup,
    regenerate_multiple_items_service,
    regenerate_setup_section,
    regenerate_single_item,
    start_adventure,
    validate_setup,
)

rpg_adventure_bp = APIRouter()


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> list:
    return list(v) if isinstance(v, (list, tuple)) else []


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


# ---------------------------------------------------------------------------
# Template listing / building
# ---------------------------------------------------------------------------


@rpg_adventure_bp.get("/api/rpg/adventure/templates")
async def adventure_templates():
    """Return available adventure setup templates with metadata."""
    try:
        templates = get_templates()
        return {"success": True, "templates": templates}
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


@rpg_adventure_bp.post("/api/rpg/adventure/template")
async def adventure_template(request: Request):
    """Build a full editable setup dict from a named template."""
    try:
        data = await request.json()
        template_name = data.get("template_name", "")
        if not template_name:
            return JSONResponse(
                {"success": False, "error": "Missing template_name"},
                status_code=400,
            )
        result = build_template_payload(template_name)
        return result
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@rpg_adventure_bp.post("/api/rpg/adventure/validate")
async def adventure_validate(request: Request):
    """Validate an adventure setup payload."""
    try:
        data = await request.json()
        result = validate_setup(data)
        validation = _safe_dict(result.get("validation"))
        return {
            "ok": not validation.get("blocking", False),
            "errors": [
                i for i in _safe_list(validation.get("issues"))
                if isinstance(i, dict) and i.get("severity") == "error"
            ],
            "warnings": _safe_list(result.get("warnings")),
            "notices": _safe_list(result.get("notices")),
            "semantic_scores": _safe_dict(result.get("semantic_scores")),
        }
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


@rpg_adventure_bp.post("/api/rpg/adventure/preview")
async def adventure_preview(request: Request):
    """Prepare a rich preview of the adventure setup."""
    try:
        data = await request.json()
        result = preview_setup(data)
        # Ensure adventure_preview is surfaced at top level
        if "adventure_preview" not in result:
            result["adventure_preview"] = _safe_dict(
                build_adventure_preview(data)
            )
        return result
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Start adventure
# ---------------------------------------------------------------------------


@rpg_adventure_bp.post("/api/rpg/adventure/start")
async def adventure_start(request: Request):
    """Create a brand-new adventure using the structured creator pipeline."""
    try:
        data = await request.json()
        result = start_adventure(data)
        return result
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Section-level regeneration
# ---------------------------------------------------------------------------


@rpg_adventure_bp.post("/api/rpg/adventure/regenerate")
async def adventure_regenerate(request: Request):
    """Regenerate a single section of an adventure setup."""
    try:
        data = await request.json()
        target = data.get("target", "")
        setup = data.get("setup", {})
        mode = data.get("mode", "apply")
        apply_token = data.get("apply_token")
        apply_strategy = data.get("apply_strategy", "replace")
        tone = data.get("tone")
        constraints = data.get("constraints")

        if not target:
            return JSONResponse(
                {"success": False, "error": "Missing target"},
                status_code=400,
            )

        result = regenerate_setup_section(
            payload=setup,
            target=target,
            mode=mode,
            apply_token=apply_token,
            apply_strategy=apply_strategy,
            tone=tone,
            constraints=constraints,
        )
        return result
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Single-item regeneration
# ---------------------------------------------------------------------------


@rpg_adventure_bp.post("/api/rpg/adventure/regenerate-item")
async def adventure_regenerate_item(request: Request):
    """Regenerate a single entity within a section."""
    try:
        data = await request.json()
        target = data.get("target", "")
        item_id = data.get("item_id", "")
        setup = data.get("setup", {})

        if not target or not item_id:
            return JSONResponse(
                {"success": False, "error": "Missing target or item_id"},
                status_code=400,
            )

        result = regenerate_single_item(
            payload=setup,
            target=target,
            item_id=item_id,
        )
        return result
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Bulk regeneration
# ---------------------------------------------------------------------------


@rpg_adventure_bp.post("/api/rpg/adventure/regenerate-multiple")
async def adventure_regenerate_multiple(request: Request):
    """Regenerate multiple entities within a section."""
    try:
        data = await request.json()
        target = data.get("target", "")
        item_ids = data.get("item_ids", [])
        setup = data.get("setup", {})

        if not target or not item_ids:
            return JSONResponse(
                {"success": False, "error": "Missing target or item_ids"},
                status_code=400,
            )

        result = regenerate_multiple_items_service(
            payload=setup,
            target=target,
            item_ids=item_ids,
        )
        return result
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# World inspection
# ---------------------------------------------------------------------------


@rpg_adventure_bp.post("/api/rpg/adventure/inspect-world")
async def adventure_inspect_world(request: Request):
    """Compute a world graph, simulation summary, and entity inspector."""
    try:
        data = await request.json()
        setup = data.get("setup", {})
        result = inspect_world(setup)
        return result
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


@rpg_adventure_bp.post("/api/rpg/adventure/inspect-world-snapshot")
async def adventure_inspect_world_snapshot(request: Request):
    """Build a full snapshot wrapper around the world inspection result."""
    try:
        data = await request.json()
        setup = data.get("setup", {})
        label = data.get("label")
        result = inspect_world_snapshot(setup, label=label)
        return result
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


@rpg_adventure_bp.post("/api/rpg/adventure/compare-world")
async def adventure_compare_world(request: Request):
    """Compare two setup payloads and return a graph diff."""
    try:
        data = await request.json()
        before_setup = data.get("before_setup", {})
        after_setup = data.get("after_setup", {})
        result = compare_world(before_setup, after_setup)
        return result
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


@rpg_adventure_bp.post("/api/rpg/adventure/compare-entity")
async def adventure_compare_entity(request: Request):
    """Compare a specific entity between two setup payloads."""
    try:
        data = await request.json()
        before_setup = data.get("before_setup", {})
        after_setup = data.get("after_setup", {})
        entity_id = data.get("entity_id", "")

        if not entity_id:
            return JSONResponse(
                {"success": False, "error": "Missing entity_id"},
                status_code=400,
            )

        from ..creator.world_snapshot import build_world_snapshot, compute_entity_diff

        before = dict(before_setup or {})
        after = dict(after_setup or {})

        before_snap = build_world_snapshot(before, label="Before")
        after_snap = build_world_snapshot(after, label="After")

        diff = compute_entity_diff(
            before_snap.get("inspector", {}),
            after_snap.get("inspector", {}),
            entity_id,
        )

        return {
            "success": True,
            "entity_id": entity_id,
            "diff": diff,
        }
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


@rpg_adventure_bp.post("/api/rpg/adventure/simulate-step")
async def adventure_simulate_step(request: Request):
    """Advance the world simulation by one tick."""
    try:
        data = await request.json()
        setup = data.get("setup", {})
        # For now, return the current setup with an incremented tick
        tick = setup.get("simulation_tick", 0) + 1
        setup["simulation_tick"] = tick
        return {
            "success": True,
            "tick": tick,
            "setup": setup,
            "health": compute_creator_health(setup),
        }
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


@rpg_adventure_bp.post("/api/rpg/adventure/simulation-state")
async def adventure_simulation_state(request: Request):
    """Get the current simulation state without advancing."""
    try:
        data = await request.json()
        setup = data.get("setup", {})
        return {
            "success": True,
            "tick": setup.get("simulation_tick", 0),
            "setup": setup,
            "health": compute_creator_health(setup),
        }
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )