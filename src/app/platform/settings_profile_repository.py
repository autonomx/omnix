"""Versioned Settings Control Center persistence over the legacy settings file."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError

from .settings_profile_core import SETTINGS_PROFILE_KEY, SETTINGS_SCHEMA_VERSION
from .settings_profile_models import SettingsProfile


class SettingsProfileValidationError(ValueError):
    def __init__(self, errors: list[dict[str, Any]]):
        super().__init__("settings profile validation failed")
        self.errors = errors


class SettingsProfileRevisionConflict(ValueError):
    def __init__(self, expected: str, actual: str):
        super().__init__("settings profile revision conflict")
        self.expected = expected
        self.actual = actual


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _merge_known(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = _copy(base)
    for key, value in patch.items():
        if key not in base or key in {"schema_version", "revision"}:
            continue
        if isinstance(base[key], dict) and isinstance(value, dict):
            merged[key] = _merge_known(base[key], value)
        else:
            merged[key] = _copy(value)
    return merged


def _revision(payload: dict[str, Any]) -> str:
    canonical = _copy(payload)
    canonical.pop("revision", None)
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _legacy_seed(settings: dict[str, Any]) -> dict[str, Any]:
    image = _record(settings.get("image"))
    return {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "global": {
            "providers": {
                "llm": str(settings.get("provider") or "lmstudio"),
                "tts": str(settings.get("audio_provider_tts") or "faster-qwen3-tts"),
                "stt": str(settings.get("audio_provider_stt") or "parakeet"),
                "image": str(image.get("provider") or ""),
            }
        },
        "rpg": {
            "image_generation": bool(image.get("enabled")),
        },
    }


def _validate_profile(profile: SettingsProfile) -> None:
    errors: list[dict[str, Any]] = []
    if profile.voice.speed < 0.5 or profile.voice.speed > 2:
        errors.append({"path": "voice.speed", "message": "must be between 0.5 and 2"})
    for path, value in [("voice.stability", profile.voice.stability), ("voice.similarity", profile.voice.similarity), ("voice.style", profile.voice.style)]:
        if value < 0 or value > 1:
            errors.append({"path": path, "message": "must be between 0 and 1"})
    for path, value in [("image.width", profile.image.width), ("image.height", profile.image.height)]:
        if value < 128 or value > 4096 or value % 64:
            errors.append({"path": path, "message": "must be 128-4096 in increments of 64"})
    if profile.storage.retention_days < 1 or profile.storage.retention_days > 3650:
        errors.append({"path": "storage.retention_days", "message": "must be between 1 and 3650"})
    if errors:
        raise SettingsProfileValidationError(errors)


def load_settings_profile(settings: dict[str, Any]) -> SettingsProfile:
    raw = settings.get(SETTINGS_PROFILE_KEY)
    source = raw if isinstance(raw, dict) else _legacy_seed(settings)
    try:
        profile = SettingsProfile.model_validate(source)
    except ValidationError as exc:
        raise SettingsProfileValidationError(exc.errors()) from exc
    payload = profile.model_dump(mode="json", by_alias=True)
    profile.revision = _revision(payload)
    _validate_profile(profile)
    return profile


def save_settings_profile(settings: dict[str, Any], patch: dict[str, Any], base_revision: str | None = None) -> SettingsProfile:
    current = load_settings_profile(settings)
    if base_revision and base_revision != current.revision:
        raise SettingsProfileRevisionConflict(base_revision, current.revision)
    current_payload = current.model_dump(mode="json", by_alias=True)
    merged = _merge_known(current_payload, _record(patch))
    try:
        profile = SettingsProfile.model_validate(merged)
    except ValidationError as exc:
        raise SettingsProfileValidationError(exc.errors()) from exc
    _validate_profile(profile)
    payload = profile.model_dump(mode="json", by_alias=True)
    profile.revision = _revision(payload)
    settings[SETTINGS_PROFILE_KEY] = profile.model_dump(mode="json", by_alias=True)
    sync_profile_to_legacy(settings, profile)
    return profile


def sync_profile_to_legacy(settings: dict[str, Any], profile: SettingsProfile) -> None:
    providers = profile.global_settings.providers
    settings["provider"] = providers.llm
    settings["audio_provider_tts"] = providers.tts
    settings["audio_provider_stt"] = providers.stt


def profile_payload(profile: SettingsProfile) -> dict[str, Any]:
    return profile.model_dump(mode="json", by_alias=True)
