"""Typed Settings Control Center adapter over legacy settings APIs."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.persistence.runtime import LegacyPersistenceRetired
from app.shared import invalidate_provider_cache, load_secrets, load_settings, save_secrets, save_settings

from .audio_cache import invalidate_changed_audio_caches
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
    # Revisions must be derived from the authoritative application-settings
    # document.  ``get_legacy_settings_payload`` overlays masked provider secrets
    # for display; including those masks in the revision makes the next save
    # conflict with the secret-free document loaded by ``save_settings_payload``.
    profile = load_settings_profile(load_settings())
    serialized_profile = profile_payload(profile)
    provider_configs = serialized_profile.get("providerConfigs", {})
    for provider_id in ("openrouter", "cerebras"):
        displayed_config = payload.settings.get(provider_id, {})
        profile_config = provider_configs.get(provider_id, {})
        if isinstance(displayed_config, dict) and isinstance(profile_config, dict):
            profile_config["apiKey"] = str(displayed_config.get("api_key") or "")
    payload.settings[SETTINGS_PROFILE_KEY] = serialized_profile
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


def _codex_profile_changed(patch: Any) -> bool:
    if not isinstance(patch, dict):
        return False
    configs = patch.get("providerConfigs")
    return isinstance(configs, dict) and "chatgptCodex" in configs


def save_settings_payload(data: dict[str, Any]) -> SettingsSaveResponse:
    """Apply compatibility and profile fields, then persist one settings document.

    The pre-PostgreSQL adapter wrote legacy settings first and the typed profile
    second. Under centralized authority that also invoked the retired plaintext
    secret writer and could leave partially updated state. This path now mutates
    one in-memory document and commits it once after all validation succeeds.
    """

    settings = load_settings()
    previous_settings = deepcopy(settings)
    secrets = load_secrets()
    legacy = _legacy_request(data)
    patch = data.get(PROFILE_PATCH_KEY)
    base_revision = data.get(PROFILE_BASE_REVISION_KEY)
    codex_profile_changed = _codex_profile_changed(patch)

    try:
        # Validate the revision against the unmodified authoritative document.
        # Applying the compatibility payload first changes the derived revision
        # and makes a combined provider/profile save conflict with itself.
        if isinstance(patch, dict) and base_revision:
            current = load_settings_profile(settings)
            if current.revision != str(base_revision):
                raise SettingsProfileRevisionConflict(str(base_revision), current.revision)

        secrets_changed = apply_settings_payload(settings, secrets, legacy) if legacy else False
        if isinstance(patch, dict):
            save_settings_profile(
                settings,
                patch,
                None,
            )
        elif legacy:
            current = load_settings_profile(settings)
            save_settings_profile(settings, _provider_patch(settings), current.revision)
        else:
            load_settings_profile(settings)

        # Provider credentials remain outside PostgreSQL. Ordinary provider/config
        # updates do not touch the OS-protected store; a real key edit is committed
        # before the authoritative settings document so failures remain atomic.
        if secrets_changed:
            save_secrets(secrets)
        save_settings(settings)
        if codex_profile_changed:
            # ChatGPT/Codex settings live only in the typed profile so the legacy
            # LLM cache fingerprint cannot see them. Force a fresh provider on the
            # next request after model/reasoning/executable changes.
            invalidate_provider_cache()
        invalidate_changed_audio_caches(previous_settings, settings)
    except (
        LegacyPersistenceRetired,
        SettingsProfileRevisionConflict,
        SettingsProfileValidationError,
    ):
        return SettingsSaveResponse(success=False)

    return SettingsSaveResponse(success=True)
