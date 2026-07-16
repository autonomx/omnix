from __future__ import annotations

import threading
import time

from app.rpg.llm_priority import RpgLlmPriorityGate


def test_waiting_foreground_runs_before_next_background_topic() -> None:
    gate = RpgLlmPriorityGate()
    first_background_started = threading.Event()
    release_first_background = threading.Event()
    order: list[str] = []

    def first_background() -> None:
        with gate.background():
            order.append("background-1")
            first_background_started.set()
            release_first_background.wait(timeout=2)

    def foreground() -> None:
        first_background_started.wait(timeout=2)
        with gate.foreground():
            order.append("foreground")

    def second_background() -> None:
        first_background_started.wait(timeout=2)
        with gate.background():
            order.append("background-2")

    threads = [
        threading.Thread(target=first_background),
        threading.Thread(target=foreground),
        threading.Thread(target=second_background),
    ]
    for thread in threads:
        thread.start()
    first_background_started.wait(timeout=2)
    deadline = time.monotonic() + 2
    while gate.snapshot()["foreground_waiters"] != 1:
        assert time.monotonic() < deadline
        time.sleep(0.001)
    release_first_background.set()
    for thread in threads:
        thread.join(timeout=2)

    assert order == ["background-1", "foreground", "background-2"]
