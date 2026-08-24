import pytest

from app.platform.settings_profile_repository import (
    SettingsProfileRevisionConflict,
    load_settings_profile,
    profile_payload,
    save_settings_profile,
)


def test_profile_contract() -> None:
    profile = load_settings_profile({"provider": "lmstudio"})
    payload = profile_payload(profile)
    assert payload["schema_version"] == 1
    assert payload["global"]["providers"]["llm"] == "lmstudio"
    assert payload["assistant"]["researchDefaultMode"] == "disabled"
    assert payload["assistant"]["researchProvider"] == "brave"
    assert payload["assistant"]["researchProviderFallbacks"] == ["playwright", "duckduckgo"]
    assert len(payload["revision"]) == 16


def test_profile_patch_preserves_defaults_and_syncs_legacy_provider() -> None:
    settings = {"provider": "lmstudio"}
    current = load_settings_profile(settings)
    saved = save_settings_profile(settings, {"global": {"providers": {"llm": "cerebras"}}, "voice": {"speed": 1.2}}, current.revision)
    assert saved.voice.speed == 1.2
    assert saved.voice.stability == 0.75
    assert settings["provider"] == "cerebras"


def test_profile_persists_research_provider_priority_budgets_and_retention() -> None:
    settings = {"provider": "lmstudio"}
    current = load_settings_profile(settings)
    saved = save_settings_profile(
        settings,
        {
            "assistant": {
                "researchProvider": "tavily",
                "researchProviderFallbacks": ["playwright", "duckduckgo"],
                "researchMaxResults": 7,
                "researchMaxSteps": 9,
                "researchMaxQueries": 6,
                "researchMaxSources": 20,
                "researchMaxExtracts": 10,
                "researchSearchCacheTtlSeconds": 600,
                "researchExtractionCacheTtlSeconds": 2400,
                "researchRawRetentionDays": 4,
                "researchManifestRetentionDays": 45,
                "researchShowDiagnostics": False,
                "researchDeepEnabled": True,
                "researchHermesPlannerEnabled": True,
            }
        },
        current.revision,
    )
    payload = profile_payload(saved)["assistant"]
    assert payload["researchProvider"] == "tavily"
    assert payload["researchProviderFallbacks"] == ["playwright", "duckduckgo"]
    assert payload["researchMaxResults"] == 7
    assert payload["researchMaxSteps"] == 9
    assert payload["researchMaxQueries"] == 6
    assert payload["researchMaxSources"] == 20
    assert payload["researchMaxExtracts"] == 10
    assert payload["researchSearchCacheTtlSeconds"] == 600
    assert payload["researchExtractionCacheTtlSeconds"] == 2400
    assert payload["researchRawRetentionDays"] == 4
    assert payload["researchManifestRetentionDays"] == 45
    assert payload["researchShowDiagnostics"] is False
    assert payload["researchDeepEnabled"] is True
    assert payload["researchHermesPlannerEnabled"] is True
    reloaded = profile_payload(load_settings_profile(settings))["assistant"]
    assert reloaded["researchProvider"] == "tavily"
    assert reloaded["researchProviderFallbacks"] == ["playwright", "duckduckgo"]
    assert reloaded["researchDeepEnabled"] is True
    assert reloaded["researchHermesPlannerEnabled"] is True


def test_profile_rejects_stale_revision() -> None:
    with pytest.raises(SettingsProfileRevisionConflict):
        save_settings_profile({"provider": "lmstudio"}, {"voice": {"speed": 1.1}}, "stale")
