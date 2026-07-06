"""Launcher composition for on-demand FLUX model residency.

The image service starts as a lightweight process, while the FLUX.2 [klein]
weights remain unloaded until the Image Generation workspace requests them.
"""
from __future__ import annotations

import os
from dataclasses import replace

from app.launcher.control_app import app
from app.launcher.service_manager import (
    LauncherServiceManager,
    build_default_service_specs,
    reset_default_manager_for_tests,
)

IMAGE_SERVICE_URL = "http://127.0.0.1:5301"


def build_runtime_service_specs():
    specs = []
    for spec in build_default_service_specs():
        if spec.service_id == "gateway":
            image_enabled = os.environ.get("OMNIX_IMAGE_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
            image_start = os.environ.get("OMNIX_START_IMAGE_SERVICE", "1").strip().lower() in {"1", "true", "yes", "on"}
            image_available = image_enabled and image_start
            specs.append(
                replace(
                    spec,
                    command=[
                        spec.command[0],
                        "-m",
                        "uvicorn",
                        "app.gateway.runtime_app:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000",
                    ],
                    env={
                        **spec.env,
                        "OMNIX_IMAGE_ENABLED": "1" if image_available else "0",
                        "OMNIX_IMAGE_URL": IMAGE_SERVICE_URL if image_available else "",
                    },
                )
            )
            continue
        if spec.service_id == "image":
            specs.append(
                replace(
                    spec,
                    env={
                        **spec.env,
                        "OMNIX_IMAGE_ENABLED": "1" if spec.enabled else "0",
                        "OMNIX_IMAGE_SERVICE_MODE": "1",
                        "OMNIX_IMAGE_PRELOAD": os.environ.get("OMNIX_IMAGE_PRELOAD", "0"),
                        "OMNIX_IMAGE_WARMUP": os.environ.get("OMNIX_IMAGE_WARMUP", "0"),
                        "OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD": os.environ.get(
                            "OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD",
                            "1",
                        ),
                        "OMNIX_IMAGE_URL": "",
                    },
                    description=(
                        "Lightweight image service on 127.0.0.1:5301. "
                        "FLUX.2 [klein] 4B stays unloaded until requested from the web UI."
                    ),
                )
            )
            continue
        specs.append(spec)
    return specs


reset_default_manager_for_tests(LauncherServiceManager(build_runtime_service_specs()))

__all__ = ["app", "build_runtime_service_specs"]
