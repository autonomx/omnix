"""Stepping a call's portrait quality level from the browser's acks (roadmap Phase 3, "Remote quality")."""
from __future__ import annotations

from app.platform.live_voice.portrait.quality import (
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


def test_a_backlog_steps_down_at_once_then_settles_before_stepping_again() -> None:
    controller = QualityController(level=0)
    for _ in range(MAX_IN_FLIGHT + 1):
        controller.relayed()
    assert controller.observe(0.0, received=0, late=0, decode_ms=5.0) == 1
    assert controller.observe(0.25, received=0, late=0, decode_ms=5.0) is None  # still draining
    assert controller.observe(SETTLE_SECONDS + 0.1, received=0, late=0, decode_ms=5.0) == 2


def test_late_frames_or_slow_decoding_step_down_and_the_lowest_level_stays() -> None:
    controller = QualityController(level=2)
    assert controller.observe(0.0, received=0, late=1, decode_ms=5.0) == 3
    assert controller.observe(5.0, received=0, late=0, decode_ms=45.0) is None  # nothing lower
    assert controller.level == 3


def test_five_healthy_seconds_step_back_up_one_level_at_a_time() -> None:
    controller = QualityController(level=2)
    assert _healthy(controller, 0.0) is None
    assert _healthy(controller, STEP_UP_SECONDS - 0.1) is None
    assert _healthy(controller, STEP_UP_SECONDS) == 1
    assert _healthy(controller, STEP_UP_SECONDS + 1.0) is None
    assert _healthy(controller, 2 * STEP_UP_SECONDS) == 0
    assert _healthy(controller, 4 * STEP_UP_SECONDS) is None  # already the best
