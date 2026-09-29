from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.rpg.persistence import (
    build_save_package,
    load_save_package,
    migrate_package_to_current,
    validate_save_package,
)

from pydantic import BaseModel as _TypedRequestBaseModel, ConfigDict as _TypedRequestConfigDict, Field as _typed_field
from typing import Any as _TypedRequestAny

class _TypedRequestModel(_TypedRequestBaseModel):
    model_config = _TypedRequestConfigDict(extra="allow", populate_by_name=True)

class ExportPackageRequestBody(_TypedRequestModel):
    setup_payload: _TypedRequestAny = None

class ValidatePackageRequestBody(_TypedRequestModel):
    package: _TypedRequestAny = None

class ImportPackageRequestBody(_TypedRequestModel):
    package: _TypedRequestAny = None


rpg_package_bp = APIRouter()


@rpg_package_bp.post("/api/rpg/package/export")
def export_package(request: Request, request_body: ExportPackageRequestBody):
    data = request_body.model_dump(exclude_unset=True, by_alias=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    package = build_save_package(setup_payload)
    return {
        "ok": True,
        "package": package,
    }


@rpg_package_bp.post("/api/rpg/package/validate")
def validate_package(request: Request, request_body: ValidatePackageRequestBody):
    data = request_body.model_dump(exclude_unset=True, by_alias=True) or {}
    package = dict(data.get("package") or {})
    migrated = migrate_package_to_current(package)
    errors = validate_save_package(migrated)
    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "package": migrated,
    }


@rpg_package_bp.post("/api/rpg/package/import")
def import_package(request: Request, request_body: ImportPackageRequestBody):
    data = request_body.model_dump(exclude_unset=True, by_alias=True) or {}
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
