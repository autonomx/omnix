from __future__ import annotations

from app.rpg.session.launcher_control_policy import build_launcher_control_policy, image_service_enabled


def test_launcher_policy_keeps_image_service_disabled_by_default() -> None:
    policy = build_launcher_control_policy({})

    assert policy["format_version"] == "rpg_launcher_control_policy_v1"
    assert policy["dashboard_single_window"] is True
    assert policy["spawn_extra_terminals_by_default"] is False
    assert policy["image_service_enabled"] is False
    assert policy["image_generation_startup_default"] == "disabled"


def test_launcher_policy_requires_both_image_env_flags() -> None:
    assert image_service_enabled({"OMNIX_IMAGE_ENABLED": "1"}) is False
    assert image_service_enabled({"OMNIX_START_IMAGE_SERVICE": "1"}) is False
    assert image_service_enabled({"OMNIX_IMAGE_ENABLED": "1", "OMNIX_START_IMAGE_SERVICE": "1"}) is True


def test_launcher_policy_lists_required_and_optional_services() -> None:
    policy = build_launcher_control_policy({"OMNIX_IMAGE_ENABLED": "1", "OMNIX_START_IMAGE_SERVICE": "1"})
    service_by_id = {service["id"]: service for service in policy["services"]}

    assert set(policy["required_service_ids"]) == {"fastapi", "stt", "tts"}
    assert policy["optional_service_ids"] == ["image"]
    assert service_by_id["fastapi"]["required"] is True
    assert service_by_id["image"]["required"] is False
    assert service_by_id["image"]["enabled"] is True


def test_launcher_policy_requires_event_bound_dashboard_controls() -> None:
    policy = build_launcher_control_policy({})

    assert policy["dashboard_controls_event_bound"] is True
    assert policy["dashboard_inline_global_handlers_allowed"] is False


def test_launcher_policy_exposes_copy_logs_contract() -> None:
    policy = build_launcher_control_policy({})

    assert policy["dashboard_copy_logs_supported"] is True
    assert policy["dashboard_copy_logs_uses_existing_log_endpoint"] is True
    assert policy["dashboard_copy_logs_browser_clipboard_only"] is True
