"""Runtime validation helpers for RPG visual providers."""
from __future__ import annotations

from typing import Any, Dict

from packaging.version import InvalidVersion, Version


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _ok_payload(provider: str, details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "provider": provider,
        "ready": True,
        "status": "ready",
        "summary": f"{provider.upper()} READY",
        "error": "",
        "details": dict(details or {}),
    }


def _fail_payload(provider: str, error: str, details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    err = _safe_str(error).strip() or "unknown_runtime_error"
    return {
        "provider": provider,
        "ready": False,
        "status": "not_ready",
        "summary": f"{provider.upper()} NOT READY",
        "error": err,
        "details": dict(details or {}),
    }


def _version_gte(value: str, minimum: str) -> bool:
    try:
        return Version(value) >= Version(minimum)
    except (InvalidVersion, TypeError):
        return False


def validate_flux_klein_runtime() -> Dict[str, Any]:
    """
    Hard runtime validation for FLUX.
    Must return structured status and never raise.
    """
    versions: Dict[str, Any] = {}

    try:
        import numpy  # noqa: F401
        versions["numpy"] = getattr(numpy, "__version__", "")
    except Exception as exc:
        return _fail_payload("flux_klein", f"numpy_import_failed:{exc!r}", {"versions": versions})

    try:
        import torch  # noqa: F401
        versions["torch"] = getattr(torch, "__version__", "")
        try:
            versions["cuda_available"] = bool(torch.cuda.is_available())
        except Exception:
            versions["cuda_available"] = False
    except Exception as exc:
        return _fail_payload("flux_klein", f"torch_import_failed:{exc!r}", {"versions": versions})

    try:
        import diffusers  # noqa: F401
        versions["diffusers"] = getattr(diffusers, "__version__", "")
    except Exception as exc:
        return _fail_payload("flux_klein", f"diffusers_import_failed:{exc!r}", {"versions": versions})

    try:
        import huggingface_hub  # noqa: F401
        versions["huggingface_hub"] = getattr(huggingface_hub, "__version__", "")
    except ImportError:
        pass

    hh_ver = versions.get("huggingface_hub", "")
    if hh_ver and _version_gte(hh_ver, "1.0.0"):
        return _fail_payload(
            "flux_klein",
            (
                "huggingface_hub_version_incompatible:"
                f"{hh_ver} — FLUX runtime expects the pinned stack from "
                "src/requirements-rpg-flux.txt. Reinstall that file in rpg-flux."
            ),
            {"versions": versions},
        )

    try:
        import transformers  # noqa: F401
        versions["transformers"] = getattr(transformers, "__version__", "")
    except ImportError as exc:
        hint = ""
        exc_str = str(exc)
        if "is_offline_mode" in exc_str and "huggingface_hub" in exc_str:
            hint = (
                " — installed huggingface_hub is incompatible with installed "
                "transformers. Reinstall the pinned FLUX stack with: "
                "pip install -r src/requirements-rpg-flux.txt"
            )
        return _fail_payload(
            "flux_klein",
            f"transformers_import_failed:{exc!r}{hint}",
            {"versions": versions},
        )
    except Exception as exc:
        return _fail_payload("flux_klein", f"transformers_import_failed:{exc!r}", {"versions": versions})

    try:
        import accelerate  # noqa: F401
        versions["accelerate"] = getattr(accelerate, "__version__", "")
    except Exception as exc:
        return _fail_payload("flux_klein", f"accelerate_import_failed:{exc!r}", {"versions": versions})

    try:
        import safetensors  # noqa: F401
        versions["safetensors"] = getattr(safetensors, "__version__", "")
    except Exception as exc:
        return _fail_payload("flux_klein", f"safetensors_import_failed:{exc!r}", {"versions": versions})

    try:
        # Verify that the installed diffusers build exposes a FLUX pipeline API.
        # Do not hard-require a nonstandard symbol like Flux2KleinPipeline here.
        from diffusers import FluxPipeline  # noqa: F401
    except Exception as exc:
        error = f"flux_pipeline_import_failed:{exc!r}"
        return _fail_payload(
            "flux_klein",
            error,
            {
                "versions": versions,
                "hint": (
                    "diffusers is installed, but the expected FLUX pipeline API is not importable. "
                    "Check the pinned diffusers version and the provider integration."
                ),
            },
        )

    return _ok_payload("flux_klein", {"versions": versions})


def log_flux_klein_runtime_status() -> Dict[str, Any]:
    status = validate_flux_klein_runtime()
    if status.get("ready"):
        print(f"[RPG][VISUAL][FLUX] FLUX READY {status.get('details', {})}")
    else:
        print(
            f"[RPG][VISUAL][FLUX] FLUX NOT READY "
            f"error={status.get('error')} details={status.get('details', {})}"
        )
    return status