from __future__ import annotations

import threading
import time
import os
import subprocess
import sys
from pathlib import Path

from app.providers.tts_priority import TtsGenerationGate, TtsPriority, other_process_priority_pending


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


def test_other_process_realtime_signal_survives_and_cleans_up_after_crash(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_BLOB_ROOT", str(tmp_path))
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[3])
    child = subprocess.Popen(
        [sys.executable, "-c", """
import time
from app.providers.tts_priority import generation_class, generation_slot
with generation_class('realtime'):
    with generation_slot():
        print('ready', flush=True)
        time.sleep(30)
"""],
        env=child_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "ready"
        assert other_process_priority_pending()
    finally:
        child.kill()
        child.communicate(timeout=5)
    time.sleep(1.1)
    assert not other_process_priority_pending()
