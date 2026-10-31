"""Stepping a call's portrait quality level from the browser's acks (roadmap Phase 3, "Remote quality")."""
from __future__ import annotations

from app.platform.live_voice.portrait.quality import (
    BACKLOG_ACKS,
    MAX_IN_FLIGHT,
    SETTLE_SECONDS,
    STEP_UP_SECONDS,
    QualityController,
    starting_level,
)


def _healthy(controller: QualityController, now: float) -> int | None:
    return controller.observe(now, received=controller.sent, late=0, decode_ms=5.0)


def test_loopback_clients_start_at_the_best_level_and_remote_ones_one_lower() -> None:
    assert starting_level("127.0.0.1") == 0 and starting_level("::1") == 0
    assert starting_level("192.168.1.20") == 1 and starting_level(None) == 1


def test_a_burst_that_drains_is_not_congestion_but_a_lasting_backlog_steps_down() -> None:
    controller = QualityController(level=0)
    for _ in range(MAX_IN_FLIGHT + 1):
        controller.relayed()
    # The service rendered ahead of playback: one ack sees a burst, the next sees it drained.
    assert controller.observe(0.0, received=0, late=0, decode_ms=5.0) is None
    assert controller.observe(0.25, received=controller.sent, late=0, decode_ms=5.0) is None
    for _ in range(MAX_IN_FLIGHT + 1):
        controller.relayed()
    stuck = controller.sent - MAX_IN_FLIGHT - 1
    results = [controller.observe(0.5 + index * 0.25, received=stuck, late=0, decode_ms=5.0)
               for index in range(BACKLOG_ACKS)]
    assert results == [None] * (BACKLOG_ACKS - 1) + [1]
    assert controller.observe(1.5, received=stuck, late=1, decode_ms=5.0) is None  # still settling
    assert controller.observe(1.0 + SETTLE_SECONDS + 0.5, received=stuck, late=1, decode_ms=5.0) == 2


def test_late_frames_step_down_slow_decoding_alone_does_not_and_the_lowest_level_stays() -> None:
    assert QualityController(level=1).observe(0.0, received=0, late=0, decode_ms=45.0) is None
    controller = QualityController(level=2)
    assert controller.observe(0.0, received=0, late=1, decode_ms=5.0) == 3
    assert controller.observe(5.0, received=0, late=2, decode_ms=5.0) is None  # nothing lower
    assert controller.level == 3


def test_five_healthy_seconds_step_back_up_one_level_at_a_time() -> None:
    controller = QualityController(level=2)
    assert _healthy(controller, 0.0) is None
    assert _healthy(controller, STEP_UP_SECONDS - 0.1) is None
    assert _healthy(controller, STEP_UP_SECONDS) == 1
    assert _healthy(controller, STEP_UP_SECONDS + 1.0) is None
    assert _healthy(controller, 2 * STEP_UP_SECONDS) == 0
    assert _healthy(controller, 4 * STEP_UP_SECONDS) is None  # already the best
