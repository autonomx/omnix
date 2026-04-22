"""Compatibility wrapper for legacy RPG runtime status imports."""
from __future__ import annotations

from app.image.runtime_status import validate_global_flux_klein_runtime, validate_global_image_runtime

def validate_flux_klein_runtime():
    return validate_global_flux_klein_runtime()


def log_flux_klein_runtime_status():
    return validate_global_flux_klein_runtime()


def validate_visual_runtime(provider_key: str | None = None):
    return validate_global_image_runtime()


def log_visual_runtime_status(provider_key: str | None = None):
    return validate_global_image_runtime()
