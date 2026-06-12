from __future__ import annotations

import os
from typing import Any, Mapping

IMAGE_GENERATION_POLICY_VERSION = "rpg_image_generation_policy_v1"


def _enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def build_rpg_image_generation_policy(env: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the RPG-facing image-generation policy.

    Image generation is intentionally external to RPG simulation/runtime. The
    default policy keeps resource-heavy providers disabled at app startup and
    requires explicit opt-in before any image service should be launched, warmed,
    or treated as available by RPG UI/runtime code.
    """

    source = env if env is not None else os.environ
    image_enabled = _enabled(source.get("OMNIX_IMAGE_ENABLED"))
    start_service = _enabled(source.get("OMNIX_START_IMAGE_SERVICE"))
    return {
        "format_version": IMAGE_GENERATION_POLICY_VERSION,
        "enabled": bool(image_enabled),
        "startup_service_allowed": bool(image_enabled and start_service),
        "runtime_provider_allowed": bool(image_enabled),
        "preload_allowed": bool(image_enabled and _enabled(source.get("OMNIX_IMAGE_PRELOAD"))),
        "warmup_allowed": bool(image_enabled and _enabled(source.get("OMNIX_IMAGE_WARMUP"))),
        "default_provider_when_disabled": "mock",
        "simulation_authority": False,
        "presentation_only": True,
        "required_enable_env": "OMNIX_IMAGE_ENABLED=1",
        "required_startup_env": "OMNIX_START_IMAGE_SERVICE=1",
    }


def is_rpg_image_generation_enabled(env: Mapping[str, Any] | None = None) -> bool:
    return bool(build_rpg_image_generation_policy(env).get("enabled"))
