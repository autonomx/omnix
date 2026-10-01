from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.persistence.device_permits import (
    DevicePermitError,
    DeviceModelOwnerLease,
    PostgresDevicePermitService,
    _DeviceModelOwnerGuard,
)


@pytest.mark.parametrize(
    ("model_class", "holder_id", "units", "priority", "lease_seconds"),
    [
        ("unknown", "worker", 1, "interactive", 30),
        ("tts", "", 1, "interactive", 30),
        ("tts", "worker", 0, "interactive", 30),
        ("tts", "worker", 1, "urgent", 30),
        ("tts", "worker", 1, "interactive", 2),
    ],
)
def test_device_permit_requests_validate_resource_identity_and_bounds(
    model_class,
    holder_id,
    units,
    priority,
    lease_seconds,
) -> None:
    with pytest.raises(ValueError):
        PostgresDevicePermitService._validate_request(
            model_class,
            holder_id,
            units,
            priority,
            lease_seconds,
        )


def test_local_tts_owner_policy_rejects_the_non_owner_process_before_model_load() -> None:
    service = PostgresDevicePermitService(
        object(),
        device_id="host-a:gpu0",
        tts_model_owner="gateway",
    )

    with pytest.raises(DevicePermitError, match="configured for gateway"):
        service.hold_model_owner(
            "tts",
            holder_id="job-worker:42",
            process_role="job-worker",
        )


def test_model_owner_loss_callback_is_applied_when_registered_after_loss() -> None:
    class Service:
        lease_seconds = 5

        def renew_model_owner(self, _lease):
            return True

        def release_model_owner(self, _lease):
            return True

    lease = DeviceModelOwnerLease(
        device_id="host-a:gpu0",
        model_class="tts",
        holder_id="gateway:123",
        lease_token="token",
        lease_expires_at=datetime.now(timezone.utc),
    )
    guard = _DeviceModelOwnerGuard(Service(), lease)
    stopped = []
    try:
        guard._notify_lost()
        assert guard.set_on_lost(lambda: stopped.append(True)) is False
        assert stopped == [True]
    finally:
        guard.close()
