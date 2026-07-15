from __future__ import annotations

from app.desktop_companion.coordinator import DesktopVisionCoordinator


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_foreground_work_outranks_background_and_single_flight_is_global():
    clock = Clock()
    coordinator = DesktopVisionCoordinator(clock=clock)
    background = coordinator.submit(
        session_id="chat-1",
        capture_generation="capture-1",
        client_sequence=1,
        priority="background",
        ttl_seconds=12,
        payload={"image": "secret"},
    )
    foreground = coordinator.submit(
        session_id="chat-2",
        capture_generation="capture-2",
        client_sequence=1,
        priority="foreground",
        ttl_seconds=12,
        payload={"image": "manual"},
    )

    first = coordinator.claim_next()
    assert first is not None
    assert first.work.request_id == foreground.request_id
    assert coordinator.claim_next() is None
    coordinator.complete(first.lease_id)

    second = coordinator.claim_next()
    assert second is not None
    assert second.work.request_id == background.request_id


def test_background_work_coalesces_by_session_and_generation():
    clock = Clock()
    coordinator = DesktopVisionCoordinator(clock=clock)
    coordinator.submit(
        session_id="chat-1",
        capture_generation="capture-1",
        client_sequence=1,
        priority="background",
        ttl_seconds=12,
        payload={"frame": 1},
    )
    latest = coordinator.submit(
        session_id="chat-1",
        capture_generation="capture-1",
        client_sequence=2,
        priority="background",
        ttl_seconds=12,
        payload={"frame": 2},
    )

    snapshot = coordinator.snapshot()
    assert snapshot.background_pending == 1
    assert snapshot.coalesced == 1
    lease = coordinator.claim_next()
    assert lease is not None
    assert lease.work.request_id == latest.request_id
    assert lease.work.client_sequence == 2


def test_background_budget_and_interval_do_not_block_foreground():
    clock = Clock()
    coordinator = DesktopVisionCoordinator(
        clock=clock,
        background_calls_per_minute=1,
        minimum_background_interval_seconds=8,
    )
    coordinator.submit(
        session_id="chat-1",
        capture_generation="capture-1",
        client_sequence=1,
        priority="background",
        ttl_seconds=120,
        payload={},
    )
    first = coordinator.claim_next()
    assert first is not None
    coordinator.complete(first.lease_id)

    coordinator.submit(
        session_id="chat-2",
        capture_generation="capture-2",
        client_sequence=1,
        priority="background",
        ttl_seconds=120,
        payload={},
    )
    assert coordinator.claim_next() is None
    assert coordinator.next_background_eligible_in() == 60

    coordinator.submit(
        session_id="chat-3",
        capture_generation="capture-3",
        client_sequence=1,
        priority="foreground",
        ttl_seconds=12,
        payload={},
    )
    foreground = coordinator.claim_next()
    assert foreground is not None
    assert foreground.work.priority == "foreground"


def test_canceled_or_stale_generation_results_are_rejected():
    clock = Clock()
    coordinator = DesktopVisionCoordinator(clock=clock)
    coordinator.submit(
        session_id="chat-1",
        capture_generation="capture-1",
        client_sequence=1,
        priority="background",
        ttl_seconds=5,
        payload={},
    )
    lease = coordinator.claim_next()
    assert lease is not None
    coordinator.cancel_generation(session_id="chat-1", capture_generation="capture-1")
    assert coordinator.accepts_result(lease) is False
    coordinator.complete(lease.lease_id)

    coordinator.submit(
        session_id="chat-2",
        capture_generation="capture-2",
        client_sequence=1,
        priority="foreground",
        ttl_seconds=2,
        payload={},
    )
    stale = coordinator.claim_next()
    assert stale is not None
    clock.advance(2)
    assert coordinator.accepts_result(stale) is False
