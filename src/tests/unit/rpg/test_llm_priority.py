from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from app.rpg.llm_priority import RpgLlmPriorityGate


def test_priority_gate_allows_at_most_four_background_calls() -> None:
    gate = RpgLlmPriorityGate(max_background=99)
    four_entered = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    active = 0
    peak = 0

    def background_call() -> None:
        nonlocal active, peak
        with gate.background():
            with lock:
                active += 1
                peak = max(peak, active)
                if active == 4:
                    four_entered.set()
            release.wait(timeout=2)
            with lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(background_call) for _ in range(5)]
        assert four_entered.wait(timeout=2)
        assert gate.snapshot()["background_active_count"] == 4
        release.set()
        for future in futures:
            future.result(timeout=2)

    assert peak == 4
    assert gate.snapshot()["background_active_count"] == 0
