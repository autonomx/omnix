"""Sanitized settings summary for the web gateway."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field


class SettingsPayload(BaseModel):
    success: bool = True
    provider: str
    audio_provider_tts: str
    audio_provider_stt: str
    image_enabled: bool
    rpg_visual_enabled: bool
    worker_urls: dict[str, str] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


class SettingsSaveResponse(BaseModel):
    success: bool = True


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_copy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = _deep_copy(value)
    return merged


def _merge_settings_section(settings: dict[str, Any], key: str, incoming: Any, default: dict[str, Any] | None = None) -> None:
    existing = _safe_dict(settings.get(key))
    fallback = _deep_copy(default or {})
    settings[key] = _deep_merge(_deep_merge(fallback, existing), _safe_dict(incoming))


def _without_api_key(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "api_key"}


def _masked_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    return f"***{api_key[-4:]}" if len(api_key) > 4 else "****"


def get_legacy_settings_payload() -> dict[str, Any]:
    from app.shared import load_secrets, load_settings

    settings = _deep_copy(load_settings())
    secrets = load_secrets()
    api_keys = _safe_dict(secrets.get("api_keys"))

    for key in ["openrouter", "cerebras"]:
        secret_key = str(api_keys.get(key) or "")
        provider_settings = _safe_dict(settings.get(key))
        if secret_key:
            provider_settings["api_key"] = secret_key
            settings[key] = provider_settings
        if provider_settings.get("api_key"):
            provider_settings["api_key"] = _masked_api_key(str(provider_settings["api_key"]))

    return settings


def get_settings_payload() -> SettingsPayload:
    from app.shared import load_settings

    settings = load_settings()
    image = _safe_dict(settings.get("image"))
    visual = _safe_dict(settings.get("rpg_visual"))
    return SettingsPayload(
        provider=str(settings.get("provider") or "lmstudio"),
        audio_provider_tts=str(settings.get("audio_provider_tts") or ""),
        audio_provider_stt=str(settings.get("audio_provider_stt") or ""),
        image_enabled=bool(image.get("enabled")),
        rpg_visual_enabled=bool(visual.get("enabled")),
        worker_urls={
            "tts": str(settings.get("tts_worker_url") or ""),
            "stt": str(settings.get("stt_worker_url") or ""),
            "image": str(settings.get("image_worker_url") or ""),
        },
        settings=get_legacy_settings_payload(),
    )


def save_settings_payload(data: dict[str, Any]) -> SettingsSaveResponse:
    from app.shared import DEFAULT_SETTINGS, load_secrets, load_settings, save_secrets, save_settings

    settings = load_settings()
    secrets = load_secrets()

    if "provider" in data:
        settings["provider"] = data["provider"]
    if "global_system_prompt" in data:
        settings["global_system_prompt"] = data["global_system_prompt"]
    if "lmstudio" in data:
        _merge_settings_section(settings, "lmstudio", data["lmstudio"], DEFAULT_SETTINGS["lmstudio"])

    if "openrouter" in data:
        incoming = _safe_dict(data["openrouter"])
        api_key = str(incoming.get("api_key") or "")
        if api_key and not api_key.startswith("***"):
            secrets.setdefault("api_keys", {})["openrouter"] = api_key
        _merge_settings_section(
            settings,
            "openrouter",
            {key: value for key, value in incoming.items() if key != "api_key"},
            _without_api_key(DEFAULT_SETTINGS["openrouter"]),
        )

    if "cerebras" in data:
        incoming = _safe_dict(data["cerebras"])
        api_key = str(incoming.get("api_key") or "")
        if api_key and not api_key.startswith("***"):
            secrets.setdefault("api_keys", {})["cerebras"] = api_key
        _merge_settings_section(
            settings,
            "cerebras",
            {key: value for key, value in incoming.items() if key != "api_key"},
            _without_api_key(DEFAULT_SETTINGS["cerebras"]),
        )

    if "llamacpp" in data:
        _merge_settings_section(settings, "llamacpp", data["llamacpp"], DEFAULT_SETTINGS["llamacpp"])

    for key in ["audio_provider_tts", "audio_provider_stt", "tts_worker_url", "stt_worker_url", "image_worker_url"]:
        if key in data:
            settings[key] = data[key]

    for key in ["faster-qwen3-tts", "parakeet", "image", "rpg_visual"]:
        if key in data:
            _merge_settings_section(settings, key, data[key], _safe_dict(DEFAULT_SETTINGS.get(key)))

    save_secrets(secrets)
    save_settings(settings)
    return SettingsSaveResponse()
