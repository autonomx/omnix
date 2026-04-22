"""Global image runtime status helpers."""
from __future__ import annotations

import os
from typing import Any, Dict

from app.image.config import get_active_image_provider_name
from app.image.downloads import get_flux_local_model_status, resolve_flux_local_dir_from_settings
from app.image.flux_pipeline_compat import validate_flux_pipeline_import, validate_flux_repo_runtime


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_global_flux_klein_runtime() -> Dict[str, Any]:
    from app.shared import load_settings
    settings = load_settings()
    local_dir = resolve_flux_local_dir_from_settings(settings)
    local_status = get_flux_local_model_status(local_dir)
    compat = validate_flux_pipeline_import()
    repo_runtime = {}
    if local_status.get("complete"):
        repo_runtime = validate_flux_repo_runtime(local_dir)

    return {
        "ok": bool(compat.get("ok")) and bool(local_status.get("complete")) and bool(repo_runtime.get("ok", True)),
        "provider": "flux_klein",
        "local_dir": os.path.normpath(local_dir),
        "local_status": local_status,
        "runtime": compat,
        "repo_runtime": repo_runtime,
    }


def validate_global_image_runtime() -> Dict[str, Any]:
    provider = get_active_image_provider_name()
    if provider == "flux_klein":
        return validate_global_flux_klein_runtime()
    if provider == "mock":
        return {
            "ok": True,
            "provider": "mock",
            "local_dir": "",
            "local_status": {"ok": True, "exists": False, "complete": True, "missing": []},
            "runtime": {"ok": True, "details": {"provider": "mock"}},
            "repo_runtime": {},
        }
    return {
        "ok": False,
        "provider": provider,
        "error": "unsupported_image_provider",
    }
