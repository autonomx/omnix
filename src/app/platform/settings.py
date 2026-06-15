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
        settings.setdefault("lmstudio", {}).update(_safe_dict(data["lmstudio"]))

    if "openrouter" in data:
        incoming = _safe_dict(data["openrouter"])
        api_key = str(incoming.get("api_key") or "")
        if api_key and not api_key.startswith("***"):
            secrets.setdefault("api_keys", {})["openrouter"] = api_key
        settings.setdefault("openrouter", {}).update({key: value for key, value in incoming.items() if key != "api_key"})

    if "cerebras" in data:
        incoming = _safe_dict(data["cerebras"])
        api_key = str(incoming.get("api_key") or "")
        if api_key and not api_key.startswith("***"):
            secrets.setdefault("api_keys", {})["cerebras"] = api_key
        settings.setdefault("cerebras", {}).update({key: value for key, value in incoming.items() if key != "api_key"})

    if "llamacpp" in data:
        settings.setdefault("llamacpp", _deep_copy(DEFAULT_SETTINGS["llamacpp"])).update(_safe_dict(data["llamacpp"]))

    save_secrets(secrets)
    save_settings(settings)
    return SettingsSaveResponse()
