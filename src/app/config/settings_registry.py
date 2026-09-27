"""Typed user-setting registry for the browser settings service."""
from __future__ import annotations

from .settings_service import SettingSpec

CORE_SETTING_SPECS: tuple[SettingSpec, ...] = (
    SettingSpec("provider", str, "lmstudio"),
    SettingSpec("global_system_prompt", str, ""),
    SettingSpec("lmstudio", dict, {"base_url": "http://localhost:1234", "direct": False}),
    SettingSpec("openrouter", dict, {"model": "openai/gpt-4o-mini", "context_size": 128000, "thinking_budget": 0}),
    SettingSpec("cerebras", dict, {"model": "llama-3.3-70b-versatile"}),
    SettingSpec("llamacpp", dict, {"base_url": "http://localhost:8080", "model": "", "download_location": "server", "auto_start": False}),
    SettingSpec("audio_provider_tts", str, "faster-qwen3-tts"),
    SettingSpec("audio_provider_stt", str, "parakeet"),
    SettingSpec("tts_worker_url", str, ""),
    SettingSpec("stt_worker_url", str, ""),
    SettingSpec("image_worker_url", str, ""),
    SettingSpec("faster-qwen3-tts", dict, {}),
    SettingSpec("parakeet", dict, {"base_url": "http://127.0.0.1:5201"}),
    SettingSpec("image", dict, {"enabled": False, "provider": "flux_klein"}),
    SettingSpec("rpg_visual", dict, {"enabled": False, "provider": "mock"}),
    SettingSpec("settings_control_center", dict, {}),
)


def core_setting_specs() -> tuple[SettingSpec, ...]:
    return CORE_SETTING_SPECS
