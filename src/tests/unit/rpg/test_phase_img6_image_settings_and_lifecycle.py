from app.image.lifecycle import unload_all_image_providers
from app.image.settings_api import (
    get_image_settings_payload,
    update_image_settings_payload,
)


def test_get_image_settings_payload_returns_ok():
    payload = get_image_settings_payload()
    assert payload["ok"] is True
    assert isinstance(payload["settings"], dict)


def test_update_image_settings_payload_updates_chat_and_story():
    payload = update_image_settings_payload({
        "enabled": True,
        "provider": "flux_klein",
        "chat": {"auto_generate_images": True, "style": "comic"},
        "story": {"auto_generate_scene_images": True, "style": "fantasy"},
    })
    assert payload["ok"] is True
    assert payload["settings"]["chat"]["auto_generate_images"] is True
    assert payload["settings"]["chat"]["style"] == "comic"
    assert payload["settings"]["story"]["auto_generate_scene_images"] is True
    assert payload["settings"]["story"]["style"] == "fantasy"


def test_unload_all_image_providers_is_ok():
    payload = unload_all_image_providers()
    assert payload["ok"] is True
