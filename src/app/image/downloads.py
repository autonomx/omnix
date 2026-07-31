"""Download helpers for global image models."""
from __future__ import annotations

import os
from typing import Any, Dict, List

from app.image.providers.registry import get_image_provider_definition
from app.shared import MODELS_DIR, load_settings, save_settings


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _provider_definition(provider_name: str) -> Dict[str, Any]:
    provider_name = _safe_str(provider_name).strip().lower()
    definition = get_image_provider_definition(provider_name)
    if not definition:
        raise ValueError(f"unsupported_image_provider:{provider_name}")
    return definition


def normalize_image_model_local_dir(
    provider_name: str,
    local_dir: str,
    download_dir: str,
) -> str:
    local_dir = _safe_str(local_dir).strip()
    if local_dir:
        return os.path.normpath(local_dir)

    definition = _provider_definition(provider_name)
    download_dir = _safe_str(download_dir).strip() or "image"
    root = download_dir if os.path.isabs(download_dir) else os.path.join(MODELS_DIR, download_dir)
    preferred = os.path.normpath(os.path.join(root, _safe_str(definition.get("local_dir_name"))))

    for legacy_name in definition.get("legacy_local_dir_names") or []:
        legacy = os.path.normpath(os.path.join(root, _safe_str(legacy_name)))
        if os.path.isdir(legacy):
            return legacy
    return preferred


def resolve_image_local_dir_from_settings(settings: Dict[str, Any], provider_name: str) -> str:
    provider_name = _safe_str(provider_name).strip().lower()
    settings = _safe_dict(settings)
    image_cfg = _safe_dict(settings.get("image"))
    provider_cfg = _safe_dict(image_cfg.get(provider_name))
    return normalize_image_model_local_dir(
        provider_name,
        _safe_str(provider_cfg.get("local_dir")),
        _safe_str(provider_cfg.get("download_dir")),
    )


def required_image_model_files(provider_name: str) -> List[str]:
    provider_name = _safe_str(provider_name).strip().lower()
    required = ["model_index.json"]
    if provider_name == "flux_klein":
        required.append(os.path.join("scheduler", "scheduler_config.json"))
    return required


def get_image_local_model_status(provider_name: str, local_dir: str = "") -> Dict[str, Any]:
    provider_name = _safe_str(provider_name).strip().lower()
    definition = _provider_definition(provider_name)
    local_dir = os.path.normpath(_safe_str(local_dir).strip())
    if not local_dir:
        local_dir = resolve_image_local_dir_from_settings(load_settings(), provider_name)

    if not definition.get("supports_local_model"):
        return {
            "ok": True,
            "exists": True,
            "complete": True,
            "missing": [],
            "local_dir": "",
            "provider": provider_name,
            "repo_id": "",
        }

    exists = os.path.isdir(local_dir)
    missing: List[str] = []
    if exists:
        for rel in required_image_model_files(provider_name):
            if not os.path.exists(os.path.join(local_dir, rel)):
                missing.append(rel)
    else:
        missing.extend(required_image_model_files(provider_name))

    has_weights = False
    if exists:
        for root, _dirs, files in os.walk(local_dir):
            if any(name.endswith((".safetensors", ".bin")) for name in files):
                has_weights = True
                break
    if not has_weights:
        missing.append("*.safetensors")

    complete = exists and not missing
    return {
        "ok": complete,
        "exists": exists,
        "complete": complete,
        "missing": missing,
        "local_dir": local_dir,
        "provider": provider_name,
        "repo_id": _safe_str(definition.get("repo_id")),
        "gated": bool(definition.get("gated")),
        "license": _safe_str(definition.get("license")),
    }


def download_image_model(provider_name: str) -> Dict[str, Any]:
    provider_name = _safe_str(provider_name).strip().lower()
    definition = _provider_definition(provider_name)
    if not definition.get("supports_download"):
        return {"ok": False, "provider": provider_name, "error": "image_model_download_not_supported"}

    settings = load_settings()
    image_cfg = _safe_dict(settings.get("image"))
    provider_cfg = _safe_dict(image_cfg.get(provider_name))
    repo_id = _safe_str(provider_cfg.get("repo_id")).strip() or _safe_str(definition.get("repo_id"))
    local_dir = resolve_image_local_dir_from_settings(settings, provider_name)
    os.makedirs(local_dir, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download
    except Exception as exc:
        return {"ok": False, "provider": provider_name, "error": f"huggingface_hub_missing:{exc}"}

    token = os.environ.get("HF_TOKEN", "").strip() or None
    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            local_dir_use_symlinks=False,
            token=token,
        )
    except Exception as exc:
        hint = ""
        if definition.get("gated"):
            hint = ": accept the model license on Hugging Face and set HF_TOKEN"
        return {
            "ok": False,
            "provider": provider_name,
            "error": f"{provider_name}_download_failed:{exc}{hint}",
            "repo_id": repo_id,
            "local_dir": local_dir,
            "gated": bool(definition.get("gated")),
        }

    provider_cfg = dict(provider_cfg)
    provider_cfg.update({
        "repo_id": repo_id,
        "local_dir": local_dir,
        "download_dir": "image",
        "prefer_local_files": True,
        "allow_repo_fallback": False,
    })
    image_cfg[provider_name] = provider_cfg
    settings["image"] = image_cfg

    # Keep the legacy RPG FLUX config in sync without changing the active model.
    if provider_name == "flux_klein":
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
    local_status = get_image_local_model_status(provider_name, local_dir)
    return {
        "ok": bool(local_status.get("complete")),
        "provider": provider_name,
        "repo_id": repo_id,
        "local_dir": local_dir,
        "local_status": local_status,
        "loaded": False,
        "downloaded_via": "/api/image-generation/model/download",
    }


# Backward-compatible FLUX helpers used by existing routes and tests.
def normalize_flux_local_dir(local_dir: str, download_dir: str) -> str:
    return normalize_image_model_local_dir("flux_klein", local_dir, download_dir)


def resolve_flux_local_dir_from_settings(settings: Dict[str, Any]) -> str:
    return resolve_image_local_dir_from_settings(settings, "flux_klein")


def required_flux_files() -> List[str]:
    return required_image_model_files("flux_klein")


def get_flux_local_model_status(local_dir: str) -> Dict[str, Any]:
    return get_image_local_model_status("flux_klein", local_dir)


def download_flux_klein_model() -> Dict[str, Any]:
    return download_image_model("flux_klein")
