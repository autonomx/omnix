"""Settings Control Center over typed per-key SettingsService persistence."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.settings.access import (
    current_settings_service,
    load_secrets,
    load_settings,
    save_secrets,
    save_settings,
)
from app.settings.service import SettingRevisionConflict, SettingsPatch
from app.providers.service import invalidate_provider_cache

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
    settings = load_settings()
    profile = load_settings_profile(settings)
    serialized_profile = profile_payload(profile)
    provider_configs = serialized_profile.get("providerConfigs", {})
    for provider_id in ("openrouter", "cerebras"):
        displayed = payload.settings.get(provider_id, {})
        profile_config = provider_configs.get(provider_id, {})
        if isinstance(displayed, dict) and isinstance(profile_config, dict):
            profile_config["apiKey"] = str(displayed.get("api_key") or "")
    payload.settings[SETTINGS_PROFILE_KEY] = serialized_profile
    return payload


def _legacy_request(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in data.items()
        if key not in {PROFILE_PATCH_KEY, PROFILE_BASE_REVISION_KEY}
    }


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


def _changed_values(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in after.items()
        if before.get(key) != value
    }


def save_settings_payload(data: dict[str, Any]) -> SettingsSaveResponse:
    service = current_settings_service()
    settings = load_settings()
    previous_settings = deepcopy(settings)
    secrets = load_secrets()
    legacy = _legacy_request(data)
    patch = data.get(PROFILE_PATCH_KEY)
    base_revision = data.get(PROFILE_BASE_REVISION_KEY)
    codex_profile_changed = _codex_profile_changed(patch)

    try:
        if isinstance(patch, dict) and base_revision:
            current = load_settings_profile(settings)
            if current.revision != str(base_revision):
                raise SettingsProfileRevisionConflict(
                    str(base_revision),
                    current.revision,
                )

        secrets_changed = apply_settings_payload(settings, secrets, legacy) if legacy else False
        if isinstance(patch, dict):
            save_settings_profile(settings, patch, None)
        elif legacy:
            current = load_settings_profile(settings)
            save_settings_profile(settings, _provider_patch(settings), current.revision)
        else:
            load_settings_profile(settings)

        changed = _changed_values(previous_settings, settings)
        revisions: dict[str, int] = {}
        for key in changed:
            current = service.get(key)
            revisions[key] = 0 if current is None else int(current["revision"])

        if secrets_changed:
            save_secrets(secrets)
        if changed:
            service.patch(SettingsPatch(values=changed, revisions=revisions))

        if codex_profile_changed:
            invalidate_provider_cache()
        invalidate_changed_audio_caches(previous_settings, settings)
    except (
        KeyError,
        PermissionError,
        SettingRevisionConflict,
        SettingsProfileRevisionConflict,
        SettingsProfileValidationError,
        TypeError,
    ):
        return SettingsSaveResponse(success=False)

    return SettingsSaveResponse(success=True)
