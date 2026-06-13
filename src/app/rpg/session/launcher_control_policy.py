from __future__ import annotations

import os
from typing import Any, Mapping

LAUNCHER_CONTROL_POLICY_VERSION = "rpg_launcher_control_policy_v1"

_REQUIRED_SERVICE_IDS = ("fastapi", "stt", "tts")
_OPTIONAL_SERVICE_IDS = ("image",)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def image_service_enabled(env: Mapping[str, Any] | None = None) -> bool:
    source = env if env is not None else os.environ
    return _truthy(source.get("OMNIX_IMAGE_ENABLED")) and _truthy(source.get("OMNIX_START_IMAGE_SERVICE"))


def build_launcher_control_policy(env: Mapping[str, Any] | None = None) -> dict[str, Any]:
    image_enabled = image_service_enabled(env)
    services = [
        {"id": service_id, "required": True, "enabled_by_default": True}
        for service_id in _REQUIRED_SERVICE_IDS
    ]
    services.append(
        {
            "id": "image",
            "required": False,
            "enabled_by_default": False,
            "enabled": image_enabled,
            "requires_env": ["OMNIX_IMAGE_ENABLED", "OMNIX_START_IMAGE_SERVICE"],
        }
    )
    return {
        "format_version": LAUNCHER_CONTROL_POLICY_VERSION,
        "source": "rpg_launcher_control_policy",
        "dashboard_single_window": True,
        "spawn_extra_terminals_by_default": False,
        "dashboard_controls_event_bound": True,
        "dashboard_inline_global_handlers_allowed": False,
        "dashboard_copy_logs_supported": True,
        "dashboard_copy_logs_uses_existing_log_endpoint": True,
        "dashboard_copy_logs_browser_clipboard_only": True,
        "required_service_ids": list(_REQUIRED_SERVICE_IDS),
        "optional_service_ids": list(_OPTIONAL_SERVICE_IDS),
        "services": services,
        "image_service_enabled": image_enabled,
        "image_generation_startup_default": "disabled",
    }
