from app.platform.settings_profile_repository import load_settings_profile, profile_payload


def test_profile_contract() -> None:
    profile = load_settings_profile({"provider": "lmstudio"})
    payload = profile_payload(profile)
    assert payload["schema_version"] == 1
    assert payload["global"]["providers"]["llm"] == "lmstudio"
    assert len(payload["revision"]) == 16
