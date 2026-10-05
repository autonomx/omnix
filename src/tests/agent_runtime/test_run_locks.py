from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from app.platform.agent_runtime.run_locks import RunLockRegistry


def test_run_lock_registry_serializes_one_run_without_blocking_other_runs():
    registry = RunLockRegistry(max_entries=1)
    first_entered = threading.Event()
    second_entered = threading.Event()
    other_run_entered = threading.Event()
    release = threading.Event()

    def hold(run_id: str, entered: threading.Event) -> None:
        with registry.hold(run_id):
            entered.set()
            assert release.wait(2)

    with ThreadPoolExecutor(max_workers=3) as executor:
        first = executor.submit(hold, "same-run", first_entered)
        try:
            assert first_entered.wait(1)
            second = executor.submit(hold, "same-run", second_entered)
            other = executor.submit(hold, "other-run", other_run_entered)

            assert other_run_entered.wait(1)
            assert not second_entered.wait(0.1)
        finally:
            release.set()

        first.result(timeout=2)
        second.result(timeout=2)
        other.result(timeout=2)

    assert second_entered.is_set()
    assert registry.retained_lock_count <= 1


def test_run_lock_registry_rejects_empty_ids_and_nonpositive_capacity():
    with pytest.raises(ValueError, match="max_entries"):
        RunLockRegistry(max_entries=0)

    registry = RunLockRegistry()
    with pytest.raises(ValueError, match="run_id"):
        with registry.hold(" "):
            pass
