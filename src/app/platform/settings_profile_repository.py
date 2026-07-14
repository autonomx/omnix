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


_PROFILE_KEY_ALIASES = {
    "schema_version": "schemaVersion",
    "voice_cloning": "voiceCloning",
    "image_prompt": "imagePrompt",
    "fallback_behavior": "fallbackBehavior",
    "task_overrides": "taskOverrides",
    "provider_id": "providerId",
    "model_id": "modelId",
    "writing_style": "writingStyle",
    "read_speed": "readSpeed",
    "pause_paragraph_ms": "pauseParagraphMs",
    "pause_chapter_ms": "pauseChapterMs",
    "read_chapter_titles": "readChapterTitles",
    "read_style_preset": "readStylePreset",
    "duration_minutes": "durationMinutes",
    "generation_style": "generationStyle",
    "playback_rate": "playbackRate",
    "cloning_language": "cloningLanguage",
    "cloning_quality": "cloningQuality",
    "world_activity": "worldActivity",
    "economy_pressure": "economyPressure",
    "combat_lethality": "combatLethality",
    "background_soft_audit": "backgroundSoftAudit",
    "llm_narration": "llmNarration",
    "image_generation": "imageGeneration",
    "campaign_defaults": "campaignDefaults",
    "hermes_assist_mode": "hermesAssistMode",
    "aspect_ratio": "aspectRatio",
    "portrait_preset": "portraitPreset",
    "scene_preset": "scenePreset",
    "unload_after_generation": "unloadAfterGeneration",
    "save_transcript": "saveTranscript",
    "microphone_device_id": "microphoneDeviceId",
    "noise_suppression": "noiseSuppression",
    "echo_cancellation": "echoCancellation",
    "save_output_by_default": "saveOutputByDefault",
    "retention_days": "retentionDays",
    "temporary_asset_cleanup": "temporaryAssetCleanup",
    "reduce_motion": "reduceMotion",
    "live_captions": "liveCaptions",
}


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _canonical_keys(value: Any) -> Any:
    if isinstance(value, list):
        return [_canonical_keys(item) for item in value]
    if not isinstance(value, dict):
        return _copy(value)
    canonical: dict[str, Any] = {}
    for key, item in value.items():
        canonical[_PROFILE_KEY_ALIASES.get(key, key)] = _canonical_keys(item)
    return canonical


def _merge_known(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = _copy(base)
    for key, value in patch.items():
        if key not in base or key in {"schemaVersion", "revision"}:
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
    lmstudio = _record(settings.get("lmstudio"))
    openrouter = _record(settings.get("openrouter"))
    cerebras = _record(settings.get("cerebras"))
    llamacpp = _record(settings.get("llamacpp"))
    qwen_tts = _record(settings.get("faster-qwen3-tts"))
    parakeet = _record(settings.get("parakeet"))
    flux = _record(image.get("flux_klein"))
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
        "providerConfigs": {
            "lmstudio": {
                "baseUrl": str(lmstudio.get("base_url") or "http://localhost:1234"),
                "model": str(lmstudio.get("model") or ""),
                "direct": bool(lmstudio.get("direct")),
            },
            "openrouter": {
                "apiKey": str(openrouter.get("api_key") or ""),
                "model": str(openrouter.get("model") or "openai/gpt-4o-mini"),
                "contextSize": int(openrouter.get("context_size") or 128000),
                "thinkingBudget": int(openrouter.get("thinking_budget") or 0),
            },
            "cerebras": {
                "apiKey": str(cerebras.get("api_key") or ""),
                "model": str(cerebras.get("model") or "llama-3.3-70b-versatile"),
            },
            "llamacpp": {
                "baseUrl": str(llamacpp.get("base_url") or "http://localhost:8080"),
                "model": str(llamacpp.get("model") or ""),
                "downloadLocation": str(llamacpp.get("download_location") or "server"),
                "autoStart": bool(llamacpp.get("auto_start")),
            },
            "fasterQwen3Tts": {
                "modelName": str(qwen_tts.get("model_name") or "Qwen/Qwen3-TTS-12Hz-0.6B-Base"),
                "modelDir": str(qwen_tts.get("model_dir") or ""),
                "device": str(qwen_tts.get("device") or "cuda"),
                "dtype": str(qwen_tts.get("dtype") or "bfloat16"),
                "chunkSize": int(qwen_tts.get("chunk_size") or 12),
                "nonStreamingMode": bool(qwen_tts.get("non_streaming_mode", True)),
            },
            "parakeet": {
                "baseUrl": str(parakeet.get("base_url") or "http://localhost:8000"),
            },
            "fluxKlein": {
                "enabled": bool(flux.get("enabled")),
                "repoId": str(flux.get("repo_id") or "black-forest-labs/FLUX.2-klein-4B"),
                "localDir": str(flux.get("local_dir") or ""),
                "device": str(flux.get("device") or "cuda"),
                "torchDtype": str(flux.get("torch_dtype") or "bfloat16"),
                "preferLocalFiles": bool(flux.get("prefer_local_files", True)),
                "allowRepoFallback": bool(flux.get("allow_repo_fallback")),
            },
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
    legacy = _legacy_seed(settings)
    default_profile = SettingsProfile.model_validate(legacy).model_dump(mode="json", by_alias=True)
    source = _merge_known(default_profile, _canonical_keys(raw)) if isinstance(raw, dict) else default_profile
    for key in ("openrouter", "cerebras"):
        legacy_key = str(_record(_record(legacy.get("providerConfigs")).get(key)).get("apiKey") or "")
        source_provider_configs = _record(source.get("providerConfigs"))
        source_config = _record(source_provider_configs.get(key))
        if legacy_key and not source_config.get("apiKey"):
            source_config["apiKey"] = legacy_key
            source_provider_configs[key] = source_config
            source["providerConfigs"] = source_provider_configs
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
    merged = _merge_known(current_payload, _canonical_keys(_record(patch)))
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
    configs = profile.provider_configs
    settings["provider"] = providers.llm
    settings["audio_provider_tts"] = providers.tts
    settings["audio_provider_stt"] = providers.stt
    settings.setdefault("lmstudio", {})
    settings["lmstudio"].update(
        {
            "base_url": configs.lmstudio.base_url,
            "model": configs.lmstudio.model,
            "direct": configs.lmstudio.direct,
        }
    )
    settings.setdefault("openrouter", {})
    settings["openrouter"].pop("api_key", None)
    settings["openrouter"].update(
        {
            "model": configs.openrouter.model,
            "context_size": configs.openrouter.context_size,
            "thinking_budget": configs.openrouter.thinking_budget,
        }
    )
    settings.setdefault("cerebras", {})
    settings["cerebras"].pop("api_key", None)
    settings["cerebras"].update({"model": configs.cerebras.model})
    settings.setdefault("llamacpp", {})
    settings["llamacpp"].update(
        {
            "base_url": configs.llamacpp.base_url,
            "model": configs.llamacpp.model,
            "download_location": configs.llamacpp.download_location,
            "auto_start": configs.llamacpp.auto_start,
        }
    )
    settings.setdefault("faster-qwen3-tts", {})
    settings["faster-qwen3-tts"].update(
        {
            "model_name": configs.faster_qwen3_tts.model_name,
            "model_dir": configs.faster_qwen3_tts.model_dir,
            "device": configs.faster_qwen3_tts.device,
            "dtype": configs.faster_qwen3_tts.dtype,
            "chunk_size": configs.faster_qwen3_tts.chunk_size,
            "non_streaming_mode": configs.faster_qwen3_tts.non_streaming_mode,
        }
    )
    settings.setdefault("parakeet", {})
    settings["parakeet"].update({"base_url": configs.parakeet.base_url})
    image = _record(settings.get("image"))
    flux = _record(image.get("flux_klein"))
    image["provider"] = providers.image.replace("image:", "") if providers.image else str(image.get("provider") or "")
    flux.update(
        {
            "enabled": configs.flux_klein.enabled,
            "repo_id": configs.flux_klein.repo_id,
            "local_dir": configs.flux_klein.local_dir,
            "device": configs.flux_klein.device,
            "torch_dtype": configs.flux_klein.torch_dtype,
            "prefer_local_files": configs.flux_klein.prefer_local_files,
            "allow_repo_fallback": configs.flux_klein.allow_repo_fallback,
        }
    )
    image["flux_klein"] = flux
    settings["image"] = image


def profile_payload(profile: SettingsProfile) -> dict[str, Any]:
    return profile.model_dump(mode="json", by_alias=True)
