from __future__ import annotations

from copy import deepcopy

from app.chat.models import CreateChatSessionRequest
from app.jobs.models import CreateJobRequest, ResourceClass


def _settings() -> dict:
    return {
        "provider": "lmstudio",
        "audio_provider_tts": "faster-qwen3-tts",
        "audio_provider_stt": "parakeet",
        "settings_control_center": {
            "global": {
                "providers": {
                    "llm": "cerebras",
                    "tts": "faster-qwen3-tts",
                    "stt": "parakeet",
                    "image": "image:flux_klein",
                    "voiceCloning": "clone-provider",
                },
                "models": {
                    "chat": "chat-model",
                    "fast": "fast-model",
                    "quality": "quality-model",
                    "background": "background-model",
                    "embedding": "embedding-model",
                    "imagePrompt": "image-prompt-model",
                },
                "routing": {
                    "fallbackBehavior": "next-available",
                    "taskOverrides": {
                        "story.generate": {"providerId": "openrouter", "modelId": "story-override"}
                    },
                },
            },
            "assistant": {
                "personalityId": "technical",
                "customPersonality": "",
                "voiceId": "voice:maya",
                "autoSpeakReplies": True,
                "speechLanguage": "en-CA",
                "streamingAudio": True,
            },
            "storyteller": {
                "providerId": "",
                "modelId": "",
                "tone": "Noir",
                "writingStyle": "Sparse",
            },
            "podcast": {
                "providerId": "",
                "modelId": "",
                "format": "interview",
                "durationMinutes": 30,
                "tone": "Conversational",
                "language": "English (CA)",
                "generationStyle": "review",
                "autoplay": True,
                "playbackRate": 1.1,
                "stability": 0.6,
                "similarity": 0.7,
                "effects": ["Compression"],
            },
            "voice": {
                "language": "French",
                "stability": 0.55,
                "similarity": 0.66,
                "style": 0.25,
                "speed": 1.2,
                "pitch": 0.1,
                "volume": -1,
                "effects": ["De-esser"],
                "streaming": True,
                "cloningLanguage": "French",
                "cloningQuality": "Studio",
            },
            "stt": {
                "language": "fr",
                "alignment": False,
                "saveTranscript": False,
                "microphoneDeviceId": "",
                "noiseSuppression": True,
                "echoCancellation": True,
            },
            "image": {
                "width": 1024,
                "height": 640,
                "aspectRatio": "16:10",
                "portraitPreset": "",
                "scenePreset": "",
                "unloadAfterGeneration": False,
            },
        },
    }


def _install(monkeypatch) -> None:
    import app.platform.effective_defaults as defaults

    settings = _settings()
    monkeypatch.setattr(defaults, "load_settings", lambda: deepcopy(settings))


def test_new_chat_uses_central_route_personality_and_voice(monkeypatch) -> None:
    _install(monkeypatch)

    request = CreateChatSessionRequest(title="New chat")

    assert request.provider_id == "cerebras"
    assert request.model_id == "chat-model"
    assert request.voice_asset_id == "voice:maya"
    assert request.system_prompt and "precise, technical" in request.system_prompt


def test_explicit_chat_session_overrides_are_preserved(monkeypatch) -> None:
    _install(monkeypatch)

    request = CreateChatSessionRequest(
        title="Explicit",
        provider_id="lmstudio",
        model_id="local-model",
        system_prompt="Session-specific prompt",
        voice_asset_id="voice:custom",
    )

    assert request.provider_id == "lmstudio"
    assert request.model_id == "local-model"
    assert request.system_prompt == "Session-specific prompt"
    assert request.voice_asset_id == "voice:custom"


def test_storyteller_job_uses_task_route_and_central_creative_defaults(monkeypatch) -> None:
    _install(monkeypatch)

    request = CreateJobRequest(
        module="storyteller",
        type="story.generate",
        resource_class=ResourceClass.GPU_LLM,
        input_payload={
            "provider_id": None,
            "model_id": None,
            "tone": "Cozy",
            "writing_style": "Lyrical & Descriptive",
        },
    )

    assert request.input_payload == {
        "provider_id": "openrouter",
        "model_id": "story-override",
        "tone": "Noir",
        "writing_style": "Sparse",
    }


def test_podcast_voice_cloning_stt_and_image_jobs_adopt_field_defaults(monkeypatch) -> None:
    _install(monkeypatch)

    podcast = CreateJobRequest(
        module="podcast",
        type="tts.multi_speaker_synthesize",
        resource_class=ResourceClass.GPU_TTS,
        input_payload={
            "format": "debate",
            "duration_minutes": 20,
            "tone": "Professional",
            "language": "English (US)",
            "generation_style": "automatic",
            "output_settings": {"stability": 0.72, "similarity": 0.78},
            "audio_effects": ["Compression", "De-esser"],
        },
    )
    assert podcast.input_payload["format"] == "interview"
    assert podcast.input_payload["duration_minutes"] == 30
    assert podcast.input_payload["tone"] == "Conversational"
    assert podcast.input_payload["language"] == "English (CA)"
    assert podcast.input_payload["output_settings"] == {"stability": 0.6, "similarity": 0.7}
    assert podcast.input_payload["audio_effects"] == ["Compression"]

    voice = CreateJobRequest(
        module="voice",
        type="tts.synthesize",
        resource_class=ResourceClass.GPU_TTS,
        input_payload={"text": "bonjour"},
    )
    assert voice.input_payload["provider_id"] == "faster-qwen3-tts"
    assert voice.input_payload["language"] == "French"
    assert voice.input_payload["output_settings"]["speed"] == 1.2
    assert voice.input_payload["audio_effects"] == ["De-esser"]

    cloning = CreateJobRequest(
        module="voice-cloning",
        type="voice-cloning.create-profile",
        resource_class=ResourceClass.GPU_TTS,
        input_payload={"profile_name": "Maya"},
    )
    assert cloning.input_payload == {
        "profile_name": "Maya",
        "provider_id": "clone-provider",
        "language": "French",
        "quality": "Studio",
    }

    stt = CreateJobRequest(
        module="stt",
        type="stt.transcribe",
        resource_class=ResourceClass.GPU_STT,
        input_payload={},
    )
    assert stt.input_payload == {
        "provider_id": "parakeet",
        "language": "fr",
        "alignment": False,
        "save_transcript": False,
    }

    image = CreateJobRequest(
        module="image-generation",
        type="image.generate",
        resource_class=ResourceClass.GPU_IMAGE,
        input_payload={"prompt": "mountains"},
    )
    assert image.input_payload["provider_id"] == "image:flux_klein"
    assert image.input_payload["width"] == 1024
    assert image.input_payload["height"] == 640
    assert image.input_payload["unload_after_generation"] is False


def test_unrelated_cpu_job_payload_is_not_mutated(monkeypatch) -> None:
    _install(monkeypatch)

    request = CreateJobRequest(
        module="maintenance",
        type="cleanup",
        resource_class=ResourceClass.CPU,
        input_payload=None,
    )

    assert request.input_payload is None
