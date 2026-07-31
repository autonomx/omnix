"""Compatibility entrypoint for the standalone image service."""
from app.image_service_runtime import app, image_model_status

__all__ = ["app", "image_model_status"]
