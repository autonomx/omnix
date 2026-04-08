from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.rpg.persistence import (
    build_save_package,
    load_save_package,
    migrate_package_to_current,
    validate_save_package,
)

rpg_package_bp = Blueprint("rpg_package_bp", __name__)


@rpg_package_bp.post("/api/rpg/package/export")
def export_package():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    package = build_save_package(setup_payload)
    return jsonify({
        "ok": True,
        "package": package,
    })


@rpg_package_bp.post("/api/rpg/package/validate")
def validate_package():
    data = request.get_json(silent=True) or {}
    package = dict(data.get("package") or {})
    migrated = migrate_package_to_current(package)
    errors = validate_save_package(migrated)
    return jsonify({
        "ok": len(errors) == 0,
        "errors": errors,
        "package": migrated,
    })


@rpg_package_bp.post("/api/rpg/package/import")
def import_package():
    data = request.get_json(silent=True) or {}
    package = dict(data.get("package") or {})
    try:
        setup_payload = load_save_package(package)
        return jsonify({
            "ok": True,
            "setup_payload": setup_payload,
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e),
        }), 400
