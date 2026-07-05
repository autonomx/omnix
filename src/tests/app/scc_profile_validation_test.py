import pytest

from app.platform.settings_profile_repository import SettingsProfileValidationError, load_settings_profile, save_settings_profile


def test_profile_validation_error_path() -> None:
    settings = {"provider": "lmstudio"}
    current = load_settings_profile(settings)
    with pytest.raises(SettingsProfileValidationError) as raised:
        save_settings_profile(settings, {"image": {"width": 777}}, current.revision)
    assert raised.value.errors[0]["path"] == "image.width"
