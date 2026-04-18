from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.rpg.persistence import (
    build_save_package,
    load_save_package,
    migrate_package_to_current,
    validate_save_package,
)

rpg_package_bp = APIRouter()


@rpg_package_bp.post("/api/rpg/package/export")
async def export_package(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    package = build_save_package(setup_payload)
    return {
        "ok": True,
        "package": package,
    }


@rpg_package_bp.post("/api/rpg/package/validate")
async def validate_package(request: Request):
    data = await request.json() or {}
    package = dict(data.get("package") or {})
    migrated = migrate_package_to_current(package)
    errors = validate_save_package(migrated)
    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "package": migrated,
    }


@rpg_package_bp.post("/api/rpg/package/import")
async def import_package(request: Request):
    data = await request.json() or {}
    package = dict(data.get("package") or {})
    try:
        setup_payload = load_save_package(package)
        return {
            "ok": True,
            "setup_payload": setup_payload,
        }
    except Exception as e:
        return JSONResponse({
            "ok": False,
            "error": str(e),
        }, status_code=400)
