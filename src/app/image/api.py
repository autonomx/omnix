"""Global image API routes."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi import Request

from app.image.downloads import download_flux_klein_model, get_flux_local_model_status
from app.image.runtime_status import validate_global_flux_klein_runtime
from app.image.service import generate_image
from app.shared import load_settings

router = APIRouter()


def _safe_dict(value):
    return value if isinstance(value, dict) else {}


@router.post("/api/image/models/flux-klein/download")
async def download_flux_klein_route():
    result = download_flux_klein_model()
    return result


@router.get("/api/image/models/flux-klein/status")
async def flux_klein_status_route():
    settings = load_settings()
    image_cfg = _safe_dict(settings.get("image"))
    flux = _safe_dict(image_cfg.get("flux_klein"))
    local_dir = flux.get("local_dir", "")
    if not local_dir:
        from app.image.downloads import resolve_flux_local_dir_from_settings
        local_dir = resolve_flux_local_dir_from_settings(settings)
    return {
        "ok": True,
        "provider": "flux_klein",
        "local_dir": local_dir,
        "local_status": get_flux_local_model_status(local_dir),
        "runtime_status": validate_global_flux_klein_runtime(),
    }


@router.post("/api/image/generate")
async def image_generate_route(request: Request):
    payload = await request.json()
    response = generate_image(payload if isinstance(payload, dict) else {})
    return {
        "ok": response.ok,
        "provider": response.provider,
        "status": response.status,
        "error": response.error,
        "asset_url": response.asset_url,
        "local_path": response.local_path,
        "seed": response.seed,
        "width": response.width,
        "height": response.height,
        "mime_type": response.mime_type,
        "metadata": response.metadata,
    }
