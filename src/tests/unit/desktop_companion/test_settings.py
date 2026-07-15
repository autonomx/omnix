from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.platform.settings_profile_experience import AssistantSettingsProfile
from app.platform.settings_profile_repository import (
    load_settings_profile,
    profile_payload,
    save_settings_profile,
)


def test_companion_settings_default_to_disabled_shadow_safe_values():
    payload = profile_payload(load_settings_profile({"provider": "lmstudio"}))["assistant"]

    assert payload["desktopCompanionEnabled"] is False
    assert payload["desktopCompanionRolloutStage"] == "disabled"
    assert payload["desktopCompanionRemoteVisionAllowed"] is False
    assert payload["desktopCompanionShowDiagnostics"] is False
    assert payload["desktopCompanionBackgroundCallsPerMinute"] == 6
    assert payload["desktopCompanionMinimumObservationIntervalMs"] == 8_000
    assert payload["desktopCompanionObservationTimeoutMs"] == 10_000
    assert payload["desktopCompanionObservationTtlMs"] == 12_000
    assert payload["desktopCompanionCommentaryCooldownMs"] == 25_000
    assert payload["desktopCompanionMinimumChangeConfidence"] == 0.55


def test_companion_settings_persist_through_shared_profile_repository():
    settings = {"provider": "lmstudio"}
    current = load_settings_profile(settings)
    saved = save_settings_profile(
        settings,
        {
            "assistant": {
                "desktopCompanionEnabled": True,
                "desktopCompanionRolloutStage": "shadow",
                "desktopCompanionVisionModelId": "qwen2.5-vl",
                "desktopCompanionRemoteVisionAllowed": False,
                "desktopCompanionShowDiagnostics": True,
                "desktopCompanionBackgroundCallsPerMinute": 4,
                "desktopCompanionMinimumObservationIntervalMs": 12_000,
                "desktopCompanionObservationTimeoutMs": 8_000,
                "desktopCompanionObservationTtlMs": 10_000,
                "desktopCompanionCommentaryCooldownMs": 30_000,
                "desktopCompanionMinimumChangeConfidence": 0.7,
            }
        },
        current.revision,
    )
    payload = profile_payload(saved)["assistant"]

    assert payload["desktopCompanionEnabled"] is True
    assert payload["desktopCompanionRolloutStage"] == "shadow"
    assert payload["desktopCompanionVisionModelId"] == "qwen2.5-vl"
    assert payload["desktopCompanionBackgroundCallsPerMinute"] == 4
    assert payload["desktopCompanionMinimumChangeConfidence"] == 0.7


def test_companion_settings_reject_unbounded_runtime_values():
    with pytest.raises(ValidationError):
        AssistantSettingsProfile(desktopCompanionBackgroundCallsPerMinute=0)
    with pytest.raises(ValidationError):
        AssistantSettingsProfile(desktopCompanionMinimumObservationIntervalMs=500)
    with pytest.raises(ValidationError):
        AssistantSettingsProfile(desktopCompanionMinimumChangeConfidence=1.5)
