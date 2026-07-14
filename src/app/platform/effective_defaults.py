"""Resolve Settings Control Center defaults at runtime without overriding explicit choices."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.shared import load_settings

from .settings_profile_models import SettingsProfile
from .settings_profile_repository import load_settings_profile

_LEGACY_CHAT_DEFAULT_PROMPT = "You are Omnix Assistant. Be helpful, clear, and practical."
_LEGACY_STORY_TONE = "Cozy"
_LEGACY_STORY_STYLE = "Lyrical & Descriptive"
_LEGACY_PODCAST_DEFAULTS: dict[str, Any] = {
    "format": "debate",
    "duration_minutes": 20,
    "tone": "Professional",
    "language": "English (US)",
    "generation_style": "automatic",
}
_PERSONALITY_PROMPTS = {
    "omnix-default": "",
    "default": "",
    "concise": "You are Omnix Assistant. Be direct, concise, and action-oriented. Prefer short answers unless detail is requested.",
    "coach": "You are Omnix Assistant. Be warm, encouraging, and practical. Ask at most one clarifying question when needed.",
    "technical": "You are Omnix Assistant. Be precise, technical, and implementation-focused. Include concrete steps and caveats.",
    "creative": "You are Omnix Assistant. Be imaginative, collaborative, and vivid while staying useful and grounded.",
}


def load_effective_profile() -> SettingsProfile:
    return load_settings_profile(load_settings())


def _text(value: Any) -> str:
    return str(value or "").strip()


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _set_if_missing(payload: dict[str, Any], key: str, value: Any) -> None:
    if not _missing(value) and _missing(payload.get(key)):
        payload[key] = deepcopy(value)


def _replace_legacy_default(payload: dict[str, Any], key: str, legacy: Any, value: Any) -> None:
    current = payload.get(key)
    if not _missing(value) and (_missing(current) or current == legacy):
        payload[key] = deepcopy(value)


def _override_value(row: dict[str, Any], camel: str, snake: str) -> str:
    return _text(row.get(camel) or row.get(snake))


def effective_llm_route(profile: SettingsProfile, module: str, task: str) -> tuple[str, str]:
    provider_id = profile.global_settings.providers.llm
    model_id = profile.global_settings.models.chat

    if module == "storyteller":
        provider_id = profile.storyteller.provider_id or provider_id
        model_id = profile.storyteller.model_id or profile.global_settings.models.quality or model_id
    elif module == "podcast":
        provider_id = profile.podcast.provider_id or provider_id
        model_id = profile.podcast.model_id or profile.global_settings.models.quality or model_id
    elif "background" in task or "audit" in task:
        model_id = profile.global_settings.models.background or model_id
    elif "fast" in task or "title" in task or "outline" in task:
        model_id = profile.global_settings.models.fast or model_id

    overrides = profile.global_settings.routing.task_overrides
    for key in (task, f"{module}:{task}", module):
        row = overrides.get(key)
        if not isinstance(row, dict):
            continue
        provider_id = _override_value(row, "providerId", "provider_id") or provider_id
        model_id = _override_value(row, "modelId", "model_id") or model_id
        break
    return provider_id, model_id


def assistant_default_prompt(profile: SettingsProfile) -> str:
    assistant = profile.assistant
    if assistant.personality_id == "custom":
        return assistant.custom_personality.strip()
    return _PERSONALITY_PROMPTS.get(assistant.personality_id, "")


def apply_chat_session_defaults(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    request = deepcopy(value)
    profile = load_effective_profile()
    provider_id, model_id = effective_llm_route(profile, "chatbot", "chat.generate")
    _set_if_missing(request, "provider_id", provider_id)
    _set_if_missing(request, "model_id", model_id)

    if request.get("interaction_mode", "system") == "system":
        current_prompt = _text(request.get("system_prompt"))
        prompt = assistant_default_prompt(profile)
        if prompt and (not current_prompt or current_prompt == _LEGACY_CHAT_DEFAULT_PROMPT):
            request["system_prompt"] = prompt
        _set_if_missing(request, "voice_asset_id", profile.assistant.voice_id)
    return request


def _apply_storyteller_defaults(payload: dict[str, Any], profile: SettingsProfile, task: str) -> None:
    provider_id, model_id = effective_llm_route(profile, "storyteller", task)
    _set_if_missing(payload, "provider_id", provider_id)
    _set_if_missing(payload, "model_id", model_id)
    _replace_legacy_default(payload, "tone", _LEGACY_STORY_TONE, profile.storyteller.tone)
    _replace_legacy_default(payload, "writing_style", _LEGACY_STORY_STYLE, profile.storyteller.writing_style)


def _apply_podcast_defaults(payload: dict[str, Any], profile: SettingsProfile) -> None:
    defaults = profile.podcast
    _replace_legacy_default(payload, "format", _LEGACY_PODCAST_DEFAULTS["format"], defaults.format)
    _replace_legacy_default(payload, "duration_minutes", _LEGACY_PODCAST_DEFAULTS["duration_minutes"], defaults.duration_minutes)
    _replace_legacy_default(payload, "tone", _LEGACY_PODCAST_DEFAULTS["tone"], defaults.tone)
    _replace_legacy_default(payload, "language", _LEGACY_PODCAST_DEFAULTS["language"], defaults.language)
    _replace_legacy_default(payload, "generation_style", _LEGACY_PODCAST_DEFAULTS["generation_style"], defaults.generation_style)
    output = payload.get("output_settings") if isinstance(payload.get("output_settings"), dict) else {}
    output = deepcopy(output)
    _replace_legacy_default(output, "stability", 0.72, defaults.stability)
    _replace_legacy_default(output, "similarity", 0.78, defaults.similarity)
    payload["output_settings"] = output
    if not payload.get("audio_effects") or payload.get("audio_effects") == ["Compression", "De-esser"]:
        payload["audio_effects"] = list(defaults.effects)


def _apply_voice_defaults(payload: dict[str, Any], profile: SettingsProfile) -> None:
    _set_if_missing(payload, "provider_id", profile.global_settings.providers.tts)
    _set_if_missing(payload, "language", profile.voice.language)
    output = payload.get("output_settings") if isinstance(payload.get("output_settings"), dict) else {}
    output = deepcopy(output)
    for key, value in {
        "stability": profile.voice.stability,
        "similarity": profile.voice.similarity,
        "style": profile.voice.style,
        "speed": profile.voice.speed,
        "pitch": profile.voice.pitch,
        "volume": profile.voice.volume,
    }.items():
        _set_if_missing(output, key, value)
    payload["output_settings"] = output
    if not payload.get("audio_effects"):
        payload["audio_effects"] = list(profile.voice.effects)


def _apply_stt_defaults(payload: dict[str, Any], profile: SettingsProfile) -> None:
    _set_if_missing(payload, "provider_id", profile.global_settings.providers.stt)
    _set_if_missing(payload, "language", profile.stt.language)
    _set_if_missing(payload, "alignment", profile.stt.alignment)
    _set_if_missing(payload, "save_transcript", profile.stt.save_transcript)


def _apply_image_defaults(payload: dict[str, Any], profile: SettingsProfile) -> None:
    _set_if_missing(payload, "provider_id", profile.global_settings.providers.image)
    _set_if_missing(payload, "width", profile.image.width)
    _set_if_missing(payload, "height", profile.image.height)
    _set_if_missing(payload, "unload_after_generation", profile.image.unload_after_generation)


def apply_job_defaults(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    request = deepcopy(value)
    payload = request.get("input_payload")
    payload = deepcopy(payload) if isinstance(payload, dict) else {}
    module = _text(request.get("module"))
    task = _text(request.get("type"))
    resource_class = _text(request.get("resource_class"))
    profile = load_effective_profile()

    if module == "storyteller":
        _apply_storyteller_defaults(payload, profile, task)
    elif module == "podcast":
        _apply_podcast_defaults(payload, profile)
    elif module in {"voice", "voice-cloning"}:
        _apply_voice_defaults(payload, profile)
    elif module == "stt":
        _apply_stt_defaults(payload, profile)
    elif module == "image-generation":
        _apply_image_defaults(payload, profile)

    if resource_class == "gpu:llm":
        provider_id, model_id = effective_llm_route(profile, module, task)
        _set_if_missing(payload, "provider_id", provider_id)
        _set_if_missing(payload, "model_id", model_id)

    request["input_payload"] = payload
    return request
