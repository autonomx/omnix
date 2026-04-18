"""Download helpers for RPG visual models."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from app.shared import MODELS_DIR, load_settings, save_settings


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _resolve_flux_klein_download_dir(settings: Dict[str, Any]) -> str:
    settings = _safe_dict(settings)
    visual = _safe_dict(settings.get("rpg_visual"))
    flux = _safe_dict(visual.get("flux_klein"))
    local_dir = _safe_str(flux.get("local_dir")).strip()
    if local_dir:
        return local_dir
    download_location = _safe_str(flux.get("download_dir")).strip() or "server"
    path = os.path.join(MODELS_DIR, download_location, "flux2-klein-4b")
    return path


def download_flux_klein_model() -> Dict[str, Any]:
    settings = load_settings()
    visual = _safe_dict(settings.get("rpg_visual"))
    flux = _safe_dict(visual.get("flux_klein"))

    variant = _safe_str(flux.get("variant")).strip().lower()
    repo_id = (
        _safe_str(flux.get("base_repo_id")).strip()
        if variant == "base"
        else _safe_str(flux.get("repo_id")).strip()
    ) or "black-forest-labs/FLUX.2-klein-4B"

    local_dir = _resolve_flux_klein_download_dir(settings)
    os.makedirs(local_dir, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download
    except Exception as exc:
        return {"ok": False, "error": f"huggingface_hub_missing:{exc}"}

    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            local_dir_use_symlinks=False,
        )
    except Exception as exc:
        return {"ok": False, "error": f"flux_klein_download_failed:{exc}"}

    visual["flux_klein"] = dict(flux)
    visual["flux_klein"]["local_dir"] = local_dir
    visual["provider"] = "flux_klein"
    settings["rpg_visual"] = visual
    save_settings(settings)

    return {
        "ok": True,
        "repo_id": repo_id,
        "local_dir": local_dir,
    }
