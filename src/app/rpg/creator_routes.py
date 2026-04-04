"""Flask Blueprint for the Creator UX v1 — Adventure Builder API.

Provides structured endpoints for template browsing, adventure setup
validation, rich preview, and launching adventures through the
``AdventureSetup`` → ``GameLoop`` pipeline.

These endpoints are separate from the legacy ``POST /api/rpg/games`` path
and are the recommended creation flow for new adventures.
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from app.rpg.services import adventure_builder_service as builder

logger = logging.getLogger(__name__)

creator_bp = Blueprint("rpg_creator", __name__)


# ---------------------------------------------------------------------------
# 1. GET /api/rpg/adventure/templates
# ---------------------------------------------------------------------------

@creator_bp.route("/api/rpg/adventure/templates", methods=["GET"])
def list_adventure_templates():
    """Return available adventure setup templates."""
    try:
        templates = builder.get_templates()
        return jsonify({"success": True, "templates": templates})
    except Exception:
        logger.exception("Failed to list templates")
        return jsonify({"success": False, "error": "Failed to list templates"}), 500


# ---------------------------------------------------------------------------
# 2. POST /api/rpg/adventure/template
# ---------------------------------------------------------------------------

@creator_bp.route("/api/rpg/adventure/template", methods=["POST"])
def build_adventure_template():
    """Build a full editable setup payload from a named template."""
    data = request.get_json() or {}
    template_name = data.get("template_name", "")

    if not template_name:
        return jsonify({"success": False, "error": "template_name is required"}), 400

    try:
        result = builder.build_template_payload(template_name)
        if not result.get("success"):
            return jsonify(result), 404
        return jsonify(result)
    except ValueError:
        return jsonify({"success": False, "error": f"Unknown template: {template_name}"}), 404
    except Exception:
        logger.exception("Failed to build template")
        return jsonify({"success": False, "error": "Failed to build template"}), 500


# ---------------------------------------------------------------------------
# 3. POST /api/rpg/adventure/validate
# ---------------------------------------------------------------------------

@creator_bp.route("/api/rpg/adventure/validate", methods=["POST"])
def validate_adventure_setup():
    """Validate a raw adventure setup payload."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Request body is required"}), 400

    try:
        result = builder.validate_setup(data)
        return jsonify(result)
    except Exception:
        logger.exception("Failed to validate setup")
        return jsonify({"success": False, "error": "Failed to validate setup"}), 500


# ---------------------------------------------------------------------------
# 4. POST /api/rpg/adventure/preview
# ---------------------------------------------------------------------------

@creator_bp.route("/api/rpg/adventure/preview", methods=["POST"])
def preview_adventure_setup():
    """Normalize, validate, and preview an adventure setup."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Request body is required"}), 400

    try:
        result = builder.preview_setup(data)
        return jsonify(result)
    except Exception:
        logger.exception("Failed to preview setup")
        return jsonify({"success": False, "error": "Failed to preview setup"}), 500


# ---------------------------------------------------------------------------
# 5. POST /api/rpg/adventure/start
# ---------------------------------------------------------------------------

@creator_bp.route("/api/rpg/adventure/start", methods=["POST"])
def start_adventure():
    """Create a brand-new adventure using the structured creator pipeline."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Request body is required"}), 400

    try:
        result = builder.start_adventure(data)
        status = 201 if result.get("success") else 400
        return jsonify(result), status
    except Exception:
        logger.exception("Failed to start adventure")
        return jsonify({"success": False, "error": "Failed to start adventure"}), 500


# ---------------------------------------------------------------------------
# 6. POST /api/rpg/adventure/regenerate
# ---------------------------------------------------------------------------

@creator_bp.route("/api/rpg/adventure/regenerate", methods=["POST"])
def regenerate_adventure_section():
    """Regenerate a single section of the adventure setup.

    Supports ``mode: "preview"`` (diff without applying) and
    ``mode: "apply"`` (apply the regeneration, optionally with merge strategy).
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Missing JSON body"}), 400

    target = data.get("target")
    payload = data.get("setup") or {}
    mode = data.get("mode", "apply")
    apply_token = data.get("apply_token")
    apply_strategy = data.get("apply_strategy", "replace")
    tone = data.get("tone")
    constraints = data.get("constraints")

    if not target:
        return jsonify({"success": False, "error": "Missing regeneration target"}), 400

    try:
        result = builder.regenerate_setup_section(
            payload,
            target,
            mode=mode,
            apply_token=apply_token,
            apply_strategy=apply_strategy,
            tone=tone,
            constraints=constraints,
        )
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception:
        logger.exception("Failed to regenerate setup section")
        return jsonify({"success": False, "error": "Failed to regenerate setup section"}), 500


# ---------------------------------------------------------------------------
# 7. POST /api/rpg/adventure/regenerate-item
# ---------------------------------------------------------------------------

@creator_bp.route("/api/rpg/adventure/regenerate-item", methods=["POST"])
def regenerate_adventure_item():
    """Regenerate a single entity within a section of the adventure setup."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Missing JSON body"}), 400

    target = data.get("target")
    item_id = data.get("item_id")
    payload = data.get("setup") or {}

    if not target:
        return jsonify({"success": False, "error": "Missing regeneration target"}), 400
    if not item_id:
        return jsonify({"success": False, "error": "Missing item_id"}), 400

    try:
        result = builder.regenerate_single_item(payload, target, item_id)
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception:
        logger.exception("Failed to regenerate single item")
        return jsonify({"success": False, "error": "Failed to regenerate single item"}), 500


# ---------------------------------------------------------------------------
# 8. POST /api/rpg/adventure/regenerate-multiple  (Phase 1.5)
# ---------------------------------------------------------------------------

@creator_bp.route("/api/rpg/adventure/regenerate-multiple", methods=["POST"])
def regenerate_multiple_items():
    """Regenerate multiple entities within a section of the adventure setup."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Missing JSON body"}), 400

    target = data.get("target")
    item_ids = data.get("item_ids") or []
    payload = data.get("setup") or {}

    if not target:
        return jsonify({"success": False, "error": "Missing regeneration target"}), 400

    try:
        result = builder.regenerate_multiple_items_service(payload, target, item_ids)
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception:
        logger.exception("Failed to regenerate multiple items")
        return jsonify({"success": False, "error": "Failed to regenerate multiple items"}), 500
