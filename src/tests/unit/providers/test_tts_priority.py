from __future__ import annotations

import threading
import time

from app.providers.tts_priority import TtsGenerationGate, TtsPriority


def test_realtime_takes_next_slot_after_active_offline_generation() -> None:
    gate = TtsGenerationGate()
    offline_started = threading.Event()
    release_offline = threading.Event()
    order: list[str] = []

    def first_offline() -> None:
        with gate.slot("offline"):
            order.append("offline-active")
            offline_started.set()
            assert release_offline.wait(2)

    def attempt(priority: TtsPriority) -> None:
        with gate.slot(priority):
            order.append(priority)

    active = threading.Thread(target=first_offline)
    active.start()
    assert offline_started.wait(2)
    realtime = threading.Thread(target=attempt, args=("realtime",))
    realtime.start()
    deadline = time.monotonic() + 2
    while gate.waiting("realtime") != 1 and time.monotonic() < deadline:
        time.sleep(0.001)
    assert gate.waiting("realtime") == 1
    next_offline = threading.Thread(target=attempt, args=("offline",))
    next_offline.start()
    release_offline.set()
    for worker in (active, realtime, next_offline):
        worker.join(2)
        assert not worker.is_alive()
    assert order == ["offline-active", "realtime", "offline"]


def test_failed_generation_releases_priority_slot() -> None:
    gate = TtsGenerationGate()
    try:
        with gate.slot("offline"):
            raise RuntimeError("provider failed")
    except RuntimeError:
        pass
    with gate.slot("realtime"):
        assert gate.waiting("offline") == 0
