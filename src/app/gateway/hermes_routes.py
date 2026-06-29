"""Compatibility module for older imports."""
from __future__ import annotations

from fastapi import FastAPI


def register_hermes_routes(app: FastAPI) -> None:
    """No-op compatibility shim."""
    return None


def install_hermes_route_hook() -> None:
    """No-op compatibility shim."""
    return None
