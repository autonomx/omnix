from __future__ import annotations

from app.platform.settings_profile_repository import load_settings_profile, profile_payload, save_settings_profile


def test_frontend_camel_case_profile_fields_round_trip() -> None:
    settings: dict = {"provider": "lmstudio"}
    current = load_settings_profile(settings)

    saved = save_settings_profile(
        settings,
        {
            "global": {
                "providers": {"voiceCloning": "faster-qwen3-tts"},
                "models": {"imagePrompt": "prompt-model"},
                "routing": {
                    "fallbackBehavior": "fail",
                    "taskOverrides": {
                        "story.generate": {"providerId": "openrouter", "modelId": "story-model"}
                    },
                },
            },
            "appearance": {"theme": "midnight", "textScale": 115, "reduceMotion": True, "liveCaptions": False},
            "voice": {"cloningLanguage": "French", "cloningQuality": "Studio"},
            "storyteller": {
                "providerId": "cerebras",
                "modelId": "quality-model",
                "writingStyle": "Sparse",
                "pauseParagraphMs": 750,
            },
            "podcast": {
                "durationMinutes": 30,
                "generationStyle": "review",
                "playbackRate": 1.2,
            },
            "rpg": {
                "worldActivity": "living_world",
                "backgroundSoftAudit": False,
                "campaignDefaults": {"genre": "noir"},
            },
            "image": {"aspectRatio": "16:9", "unloadAfterGeneration": False},
            "stt": {"saveTranscript": False, "noiseSuppression": False},
            "storage": {"retentionDays": 90, "temporaryAssetCleanup": False},
        },
        current.revision,
    )

    payload = profile_payload(saved)
    assert payload["schemaVersion"] == 1
    assert payload["global"]["providers"]["voiceCloning"] == "faster-qwen3-tts"
    assert payload["global"]["models"]["imagePrompt"] == "prompt-model"
    assert payload["global"]["routing"]["fallbackBehavior"] == "fail"
    assert payload["global"]["routing"]["taskOverrides"]["story.generate"] == {
        "providerId": "openrouter",
        "modelId": "story-model",
    }
    assert payload["appearance"] == {
        "mode": "system",
        "theme": "midnight",
        "density": "comfortable",
        "textScale": 115,
        "reduceMotion": True,
        "liveCaptions": False,
    }
    assert payload["voice"]["cloningLanguage"] == "French"
    assert payload["voice"]["cloningQuality"] == "Studio"
    assert payload["storyteller"]["providerId"] == "cerebras"
    assert payload["storyteller"]["writingStyle"] == "Sparse"
    assert payload["podcast"]["durationMinutes"] == 30
    assert payload["podcast"]["generationStyle"] == "review"
    assert payload["rpg"]["worldActivity"] == "living_world"
    assert payload["rpg"]["campaignDefaults"] == {"genre": "noir"}
    assert payload["image"]["aspectRatio"] == "16:9"
    assert payload["image"]["unloadAfterGeneration"] is False
    assert payload["stt"]["saveTranscript"] is False
    assert payload["storage"]["retentionDays"] == 90


def test_legacy_snake_case_profile_fields_remain_accepted() -> None:
    settings = {
        "provider": "lmstudio",
        "settings_control_center": {
            "schema_version": 1,
            "global": {
                "models": {"image_prompt": "legacy-prompt"},
                "routing": {"fallback_behavior": "fail", "task_overrides": {}},
            },
            "appearance": {"text_scale": 125},
            "storyteller": {"writing_style": "Legacy sparse"},
            "podcast": {"duration_minutes": 45},
            "rpg": {"world_activity": "quiet"},
            "image": {"unload_after_generation": False},
            "stt": {"save_transcript": False},
        },
    }

    payload = profile_payload(load_settings_profile(settings))

    assert payload["global"]["models"]["imagePrompt"] == "legacy-prompt"
    assert payload["global"]["routing"]["fallbackBehavior"] == "fail"
    assert payload["appearance"]["textScale"] == 125
    assert payload["storyteller"]["writingStyle"] == "Legacy sparse"
    assert payload["podcast"]["durationMinutes"] == 45
    assert payload["rpg"]["worldActivity"] == "quiet"
    assert payload["image"]["unloadAfterGeneration"] is False
    assert payload["stt"]["saveTranscript"] is False
