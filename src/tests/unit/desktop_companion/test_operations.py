from __future__ import annotations

from app.desktop_companion.operations import desktop_companion_operational_status


def test_operational_status_is_available_by_default() -> None:
    status = desktop_companion_operational_status({})

    assert status.available is True
    assert status.kill_switch is False
    assert status.raw_frame_persistence is False
    assert status.max_consecutive_provider_failures == 6


def test_deployment_kill_switch_is_explicit() -> None:
    status = desktop_companion_operational_status(
        {"OMNIX_DESKTOP_COMPANION_KILL_SWITCH": "true"}
    )

    assert status.available is False
    assert status.kill_switch is True
    assert status.reason == "deployment_kill_switch"
