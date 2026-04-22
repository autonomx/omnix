"""Download helpers for global image models."""
from __future__ import annotations

import os
from typing import Any, Dict, List

from app.shared import MODELS_DIR, load_settings, save_settings


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_flux_local_dir(local_dir: str, download_dir: str) -> str:
    local_dir = _safe_str(local_dir).strip()
    if local_dir:
        return os.path.normpath(local_dir)

    download_dir = _safe_str(download_dir).strip() or "image"
    if os.path.isabs(download_dir):
        root = download_dir
    else:
        root = os.path.join(MODELS_DIR, download_dir)

    return os.path.normpath(os.path.join(root, "flux2-klein-4b"))


def resolve_flux_local_dir_from_settings(settings: Dict[str, Any]) -> str:
    settings = _safe_dict(settings)
    image_cfg = _safe_dict(settings.get("image"))
    flux = _safe_dict(image_cfg.get("flux_klein"))
    return normalize_flux_local_dir(
        _safe_str(flux.get("local_dir")),
        _safe_str(flux.get("download_dir")),
    )


def required_flux_files() -> List[str]:
    return [
        "model_index.json",
        "tokenizer.json",
        "tokenizer_config.json",
        os.path.join("scheduler", "scheduler_config.json"),
    ]


def get_flux_local_model_status(local_dir: str) -> Dict[str, Any]:
    local_dir = os.path.normpath(_safe_str(local_dir).strip())
    if not local_dir:
        return {
            "ok": False,
            "exists": False,
            "complete": False,
            "missing": ["<local_dir_not_set>"],
            "local_dir": "",
        }

    exists = os.path.isdir(local_dir)
    missing: List[str] = []

    if exists:
        for rel in required_flux_files():
            if not os.path.exists(os.path.join(local_dir, rel)):
                missing.append(rel)
    else:
        missing.extend(required_flux_files())

    has_weights = False
    if exists:
        for root, _dirs, files in os.walk(local_dir):
            for name in files:
                if name.endswith(".safetensors"):
                    has_weights = True
                    break
            if has_weights:
                break
    if not has_weights:
        missing.append("*.safetensors")

    return {
        "ok": exists and not missing,
        "exists": exists,
        "complete": exists and not missing,
        "missing": missing,
        "local_dir": local_dir,
    }


def download_flux_klein_model() -> Dict[str, Any]:
    settings = load_settings()
    image_cfg = _safe_dict(settings.get("image"))
    flux = _safe_dict(image_cfg.get("flux_klein"))

    variant = _safe_str(flux.get("variant")).strip().lower()
    repo_id = (
        _safe_str(flux.get("base_repo_id")).strip()
        if variant == "base"
        else _safe_str(flux.get("repo_id")).strip()
    ) or "black-forest-labs/FLUX.2-klein-4B"

    local_dir = resolve_flux_local_dir_from_settings(settings)
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
        return {
            "ok": False,
            "error": f"flux_klein_download_failed:{exc}",
            "repo_id": repo_id,
            "local_dir": local_dir,
        }

    image_cfg["flux_klein"] = dict(flux)
    image_cfg["flux_klein"]["local_dir"] = local_dir
    image_cfg["flux_klein"]["download_dir"] = "image"
    image_cfg["flux_klein"]["prefer_local_files"] = True
    image_cfg["flux_klein"]["allow_repo_fallback"] = False
    image_cfg["provider"] = "flux_klein"
    settings["image"] = image_cfg

    # Keep RPG visual in sync for compatibility during migration.
    rpg_visual = _safe_dict(settings.get("rpg_visual"))
    rpg_flux = _safe_dict(rpg_visual.get("flux_klein"))
    rpg_flux.update({
        "local_dir": local_dir,
        "download_dir": "image",
        "prefer_local_files": True,
        "allow_repo_fallback": False,
    })
    rpg_visual["flux_klein"] = rpg_flux
    if not _safe_str(rpg_visual.get("provider")).strip():
        rpg_visual["provider"] = "flux_klein"
    settings["rpg_visual"] = rpg_visual

    save_settings(settings)

    local_status = get_flux_local_model_status(local_dir)
    return {
        "ok": bool(local_status.get("complete")),
        "repo_id": repo_id,
        "local_dir": local_dir,
        "local_status": local_status,
        "downloaded_via": "/api/image/models/flux-klein/download",
    }
