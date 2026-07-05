"""Typed Settings Control Center adapter over legacy settings APIs."""
from __future__ import annotations

from typing import Any

from app.shared import load_settings, save_settings

from .settings import SettingsPayload, SettingsSaveResponse
from .settings import get_settings_payload as get_legacy_settings_payload
from .settings import save_settings_payload as save_legacy_settings_payload
from .settings_profile_core import SETTINGS_PROFILE_KEY
from .settings_profile_repository import (
    SettingsProfileRevisionConflict,
    SettingsProfileValidationError,
    load_settings_profile,
    profile_payload,
    save_settings_profile,
)

PROFILE_PATCH_KEY = "settings_profile_patch"
PROFILE_BASE_REVISION_KEY = "base_revision"


def get_settings_payload() -> SettingsPayload:
    payload = get_legacy_settings_payload()
    profile = load_settings_profile(load_settings())
    payload.settings[SETTINGS_PROFILE_KEY] = profile_payload(profile)
    return payload


def _legacy_request(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key not in {PROFILE_PATCH_KEY, PROFILE_BASE_REVISION_KEY}}


def _provider_patch(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "global": {
            "providers": {
                "llm": str(settings.get("provider") or "lmstudio"),
                "tts": str(settings.get("audio_provider_tts") or "faster-qwen3-tts"),
                "stt": str(settings.get("audio_provider_stt") or "parakeet"),
            }
        }
    }


def save_settings_payload(data: dict[str, Any]) -> SettingsSaveResponse:
    legacy = _legacy_request(data)
    if legacy:
        save_legacy_settings_payload(legacy)

    settings = load_settings()
    patch = data.get(PROFILE_PATCH_KEY)
    base_revision = data.get(PROFILE_BASE_REVISION_KEY)
    try:
        if isinstance(patch, dict):
            save_settings_profile(settings, patch, str(base_revision) if base_revision else None)
        elif legacy:
            current = load_settings_profile(settings)
            save_settings_profile(settings, _provider_patch(settings), current.revision)
        else:
            load_settings_profile(settings)
    except (SettingsProfileRevisionConflict, SettingsProfileValidationError):
        return SettingsSaveResponse(success=False)

    save_settings(settings)
    return SettingsSaveResponse(success=True)
