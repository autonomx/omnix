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
    assert len(payload["revision"]) == 16


def test_profile_patch_preserves_defaults_and_syncs_legacy_provider() -> None:
    settings = {"provider": "lmstudio"}
    current = load_settings_profile(settings)
    saved = save_settings_profile(settings, {"global": {"providers": {"llm": "cerebras"}}, "voice": {"speed": 1.2}}, current.revision)
    assert saved.voice.speed == 1.2
    assert saved.voice.stability == 0.75
    assert settings["provider"] == "cerebras"


def test_profile_rejects_stale_revision() -> None:
    with pytest.raises(SettingsProfileRevisionConflict):
        save_settings_profile({"provider": "lmstudio"}, {"voice": {"speed": 1.1}}, "stale")
