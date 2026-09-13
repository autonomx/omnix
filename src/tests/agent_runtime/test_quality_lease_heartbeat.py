from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import Mock

from app.agent_runtime import quality_recovery
from app.agent_runtime.repository import AgentLeaseConflict


def test_quality_lease_heartbeat_is_independent_of_service_runtime_lock(monkeypatch) -> None:
    runtime_lock = threading.RLock()
    runtime_lock.acquire()
    heartbeats: list[tuple[str, int]] = []
    service = SimpleNamespace(
        worker_id="worker-a",
        _lock=runtime_lock,
        heartbeat=lambda run_id, ttl_seconds: heartbeats.append((run_id, ttl_seconds)),
        runtime=SimpleNamespace(close_run=Mock()),
    )
    monkeypatch.setattr(quality_recovery, "_owned_active_run_ids", lambda _service: ["run-a"])

    try:
        quality_recovery._renew_owned_leases(service)
    finally:
        runtime_lock.release()

    assert heartbeats
    assert heartbeats[0][0] == "run-a"
    assert heartbeats[0][1] >= int(quality_recovery._lease_heartbeat_interval_seconds() * 3)


def test_quality_lease_heartbeat_does_not_reacquire_lost_ownership(monkeypatch) -> None:
    close_run = Mock()

    def lost(_run_id: str, *, ttl_seconds: int) -> None:
        raise AgentLeaseConflict("owned by another worker")

    service = SimpleNamespace(
        worker_id="worker-a",
        heartbeat=lost,
        runtime=SimpleNamespace(close_run=close_run),
    )
    monkeypatch.setattr(quality_recovery, "_owned_active_run_ids", lambda _service: ["run-a"])

    quality_recovery._renew_owned_leases(service)

    close_run.assert_called_once_with("run-a")


def test_transient_heartbeat_failure_is_not_treated_as_ownership_loss(monkeypatch) -> None:
    close_run = Mock()

    def transient(_run_id: str, *, ttl_seconds: int) -> None:
        raise RuntimeError("database temporarily unavailable")

    service = SimpleNamespace(
        worker_id="worker-a",
        heartbeat=transient,
        runtime=SimpleNamespace(close_run=close_run),
    )
    monkeypatch.setattr(quality_recovery, "_owned_active_run_ids", lambda _service: ["run-a"])

    quality_recovery._renew_owned_leases(service)

    close_run.assert_not_called()


def test_quality_supervisor_starts_only_one_independent_heartbeat_thread(monkeypatch) -> None:
    started: list[tuple[object, ...]] = []

    class FakeThread:
        def __init__(self, *, target, args, name, daemon):
            assert target is quality_recovery._lease_heartbeat_loop
            assert name == "omnix-agent-lease-heartbeat"
            assert daemon is True
            self.args = args

        def start(self) -> None:
            started.append(self.args)

    service = SimpleNamespace(
        _supervisor_stop=threading.Event(),
        _quality_lease_heartbeat_started=False,
    )
    monkeypatch.setattr(quality_recovery.threading, "Thread", FakeThread)

    quality_recovery._ensure_independent_lease_heartbeat(service)
    quality_recovery._ensure_independent_lease_heartbeat(service)

    assert len(started) == 1
    assert started[0] == (service,)
    assert service._quality_lease_heartbeat_started is True
