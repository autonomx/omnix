"""Compatibility helpers for FLUX pipeline loading.

Short-term goal: keep flux_klein as the active provider without
hard-requiring one exact top-level diffusers export.
"""
from __future__ import annotations

import importlib
from typing import Any, Dict, Tuple


def resolve_flux_pipeline_class() -> Tuple[type, str]:
    """
    Resolve the usable FLUX pipeline class from diffusers.

    Order:
    1. Flux2KleinPipeline (repo-specific / custom naming)
    2. FluxPipeline (upstream / generic naming, top-level export)
    3. FluxPipeline from known submodule paths
    """
    import diffusers

    if hasattr(diffusers, "Flux2KleinPipeline"):
        return getattr(diffusers, "Flux2KleinPipeline"), "Flux2KleinPipeline"
    if hasattr(diffusers, "FluxPipeline"):
        return getattr(diffusers, "FluxPipeline"), "FluxPipeline"

    fallback_candidates = [
        ("diffusers.pipelines.flux.pipeline_flux", "FluxPipeline"),
    ]
    errors = []
    for module_name, class_name in fallback_candidates:
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, class_name):
                return getattr(module, class_name), f"{module_name}.{class_name}"
            errors.append(f"{module_name}:{class_name}:missing_attr")
        except Exception as exc:
            errors.append(f"{module_name}:{class_name}:{exc!r}")

    raise ImportError(
        "No supported FLUX pipeline class is importable from diffusers. "
        + "; ".join(errors)
    )


def validate_flux_pipeline_import() -> Dict[str, Any]:
    """
    Return structured status for FLUX pipeline compatibility.
    """
    details: Dict[str, Any] = {}

    try:
        import diffusers  # noqa: F401
        details["diffusers_version"] = getattr(diffusers, "__version__", "")
    except Exception as exc:
        return {
            "ok": False,
            "error": f"diffusers_import_failed:{exc!r}",
            "details": details,
        }

    try:
        cls, class_name = resolve_flux_pipeline_class()
        details["pipeline_class"] = class_name.split(".")[-1]
        details["pipeline_resolved_from"] = class_name
        details["pipeline_module"] = getattr(cls, "__module__", "")
        return {
            "ok": True,
            "error": "",
            "details": details,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"flux_pipeline_import_failed:{exc!r}",
            "details": details,
        }


def build_flux_pipeline(
    repo_or_path: str,
    *,
    torch_dtype: Any,
    local_files_only: bool,
):
    """
    Construct the FLUX pipeline using the resolved compatible class.
    """
    pipeline_cls, _class_name = resolve_flux_pipeline_class()
    return pipeline_cls.from_pretrained(
        repo_or_path,
        torch_dtype=torch_dtype,
        local_files_only=local_files_only,
    )