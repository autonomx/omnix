"""Compatibility entrypoint for the standalone image service."""
from __future__ import annotations

import sys

from app import image_service_runtime as _runtime

# Preserve the historical module identity so existing launchers and tests that
# monkeypatch ``app.image_service_app`` affect the functions backing ``app``.
app = _runtime.app
image_model_status = _runtime.image_model_status
sys.modules[__name__] = _runtime
