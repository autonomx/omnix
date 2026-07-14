"""Typed Settings Control Center adapter over legacy settings APIs."""
from __future__ import annotations

from typing import Any

from app.persistence.runtime import LegacyPersistenceRetired
from app.shared import load_secrets, load_settings, save_secrets, save_settings

from .settings import SettingsPayload, SettingsSaveResponse, apply_settings_payload
from .settings import get_settings_payload as get_legacy_settings_payload
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
    profile = load_settings_profile(payload.settings)
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
    """Apply compatibility and profile fields, then persist one settings document.

    The pre-PostgreSQL adapter wrote legacy settings first and the typed profile
    second. Under centralized authority that also invoked the retired plaintext
    secret writer and could leave partially updated state. This path now mutates
    one in-memory document and commits it once after all validation succeeds.
    """

    settings = load_settings()
    secrets = load_secrets()
    legacy = _legacy_request(data)
    secrets_changed = apply_settings_payload(settings, secrets, legacy) if legacy else False
    patch = data.get(PROFILE_PATCH_KEY)
    base_revision = data.get(PROFILE_BASE_REVISION_KEY)

    try:
        if isinstance(patch, dict):
            save_settings_profile(
                settings,
                patch,
                str(base_revision) if base_revision else None,
            )
        elif legacy:
            current = load_settings_profile(settings)
            save_settings_profile(settings, _provider_patch(settings), current.revision)
        else:
            load_settings_profile(settings)

        # Provider credentials are environment-owned in PostgreSQL mode. Ordinary
        # provider/config updates never call this retired writer; a real key edit
        # fails before the authoritative settings document is committed.
        if secrets_changed:
            save_secrets(secrets)
        save_settings(settings)
    except (
        LegacyPersistenceRetired,
        SettingsProfileRevisionConflict,
        SettingsProfileValidationError,
    ):
        return SettingsSaveResponse(success=False)

    return SettingsSaveResponse(success=True)
