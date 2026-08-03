"""Launcher composition for on-demand models and optional live services."""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from app.launcher.control_app import app
from app.launcher.kyutai_services import build_kyutai_service_specs
from app.launcher.service_manager import (
    LauncherServiceManager,
    build_default_service_specs,
    reset_default_manager_for_tests,
)

IMAGE_SERVICE_URL = "http://127.0.0.1:5301"


def build_runtime_service_specs():
    root = Path(__file__).resolve().parents[3]
    kyutai_specs, browser_stt_url = build_kyutai_service_specs(root)
    kyutai_enabled = any(spec.enabled for spec in kyutai_specs)
    specs = []
    kyutai_inserted = False

    for spec in build_default_service_specs(root):
        if spec.service_id == "gateway":
            if not kyutai_inserted:
                specs.extend(kyutai_specs)
                kyutai_inserted = True
            image_enabled = os.environ.get("OMNIX_IMAGE_ENABLED", "1").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            image_start = os.environ.get("OMNIX_START_IMAGE_SERVICE", "1").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            image_available = image_enabled and image_start
            specs.append(
                replace(
                    spec,
                    env={
                        **spec.env,
                        "OMNIX_IMAGE_ENABLED": "1" if image_available else "0",
                        "OMNIX_IMAGE_URL": IMAGE_SERVICE_URL if image_available else "",
                    },
                )
            )
            continue
        if spec.service_id == "web" and kyutai_enabled:
            specs.append(
                replace(
                    spec,
                    env={
                        **spec.env,
                        "VITE_ASSISTANT_STT_URL": browser_stt_url,
                        "VITE_LIVE_SPECULATION_ENABLED": os.environ.get(
                            "VITE_LIVE_SPECULATION_ENABLED",
                            "true",
                        ),
                        "VITE_LIVE_TTS_ADAPTIVE_BUFFER": os.environ.get(
                            "VITE_LIVE_TTS_ADAPTIVE_BUFFER",
                            "true",
                        ),
                    },
                    description=(
                        "React/Vite browser app on 127.0.0.1:5173. "
                        "Live voice uses Kyutai test authority with Parakeet fallback."
                    ),
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

    if not kyutai_inserted:
        specs.extend(kyutai_specs)
    return specs


reset_default_manager_for_tests(LauncherServiceManager(build_runtime_service_specs()))

__all__ = ["app", "build_runtime_service_specs"]
