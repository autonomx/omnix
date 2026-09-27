"""Browser settings API helpers backed only by SettingsService entries."""
from __future__ import annotations

from typing import Any

from app.platform.settings import SettingsPayload, SettingsSaveResponse

from .settings_registry import CORE_SETTING_SPECS
from .settings_service import SettingsPatch, SettingsService


def settings_dict(service: SettingsService | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for spec in CORE_SETTING_SPECS:
        item = service.get(spec.key) if service is not None else None
        result[spec.key] = spec.default if item is None else item["value"]
    return result


def settings_payload(service: SettingsService | None) -> SettingsPayload:
    settings = settings_dict(service)
    image = settings.get("image") if isinstance(settings.get("image"), dict) else {}
    visual = settings.get("rpg_visual") if isinstance(settings.get("rpg_visual"), dict) else {}
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
        settings=settings,
    )


def save_settings_patch(service: SettingsService, patch: SettingsPatch) -> SettingsSaveResponse:
    service.patch(patch)
    return SettingsSaveResponse(success=True)
