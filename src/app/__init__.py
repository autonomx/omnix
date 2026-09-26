"""Omnix application package. The shared gateway owns application assembly."""
from __future__ import annotations


def create_fastapi_app():
    """Return a shared gateway instance for existing application-factory callers."""
    from app.gateway.main import create_gateway_app

    return create_gateway_app()


create_app = create_fastapi_app
