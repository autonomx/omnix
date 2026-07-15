from __future__ import annotations

from app.desktop_companion.coordinator import DesktopVisionCoordinator


def test_background_queue_stays_bounded_across_ten_thousand_unique_sessions() -> None:
    coordinator = DesktopVisionCoordinator(
        clock=lambda: 1.0,
        minimum_background_interval_seconds=0,
        maximum_background_pending=64,
    )

    for index in range(10_000):
        coordinator.submit(
            session_id=f"chat:{index}",
            capture_generation=f"capture:{index}",
            client_sequence=1,
            priority="background",
            ttl_seconds=120,
            payload={"index": index},
        )

    snapshot = coordinator.snapshot()
    assert snapshot.background_pending == 64
    assert snapshot.dropped == 9_936


def test_repeated_updates_for_one_generation_coalesce_without_growth() -> None:
    coordinator = DesktopVisionCoordinator(
        clock=lambda: 1.0,
        minimum_background_interval_seconds=0,
    )

    for index in range(10_000):
        coordinator.submit(
            session_id="chat:one",
            capture_generation="capture:one",
            client_sequence=index,
            priority="background",
            ttl_seconds=120,
            payload={"index": index},
        )

    snapshot = coordinator.snapshot()
    assert snapshot.background_pending == 1
    assert snapshot.coalesced == 9_999
