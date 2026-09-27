"""Composition helper for transitional gateway registrars.

The registrar specification is owned by a FeatureModule. This helper contains
only the mechanics needed while route modules move physically out of gateway.
"""
from __future__ import annotations

from importlib import import_module
from typing import Iterable

from .features import FeatureContext


def install_registrars(
    gateway,
    context: FeatureContext,
    registrars: Iterable[tuple[str, str]],
) -> None:
    for module_name, registrar_name in registrars:
        before = (len(gateway.router.on_startup), len(gateway.router.on_shutdown))
        registrar = getattr(import_module(module_name), registrar_name)
        registrar(gateway)
        after = (len(gateway.router.on_startup), len(gateway.router.on_shutdown))
        if before != after:
            raise RuntimeError(
                f"{context.feature_id} registrar {module_name}.{registrar_name} "
                "must use FeatureLifecycle or BackgroundWorker instead of FastAPI lifecycle hooks"
            )
