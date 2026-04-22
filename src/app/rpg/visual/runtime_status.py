"""Compatibility wrapper for legacy RPG runtime status imports."""
from __future__ import annotations

from app.image.runtime_status import validate_global_flux_klein_runtime


def validate_flux_klein_runtime():
    return validate_global_flux_klein_runtime()

