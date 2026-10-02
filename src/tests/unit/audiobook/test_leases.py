import threading
from contextlib import contextmanager
from types import SimpleNamespace

from app.audiobook import leases
from app.jobs.errors import JobClaimConflict

CONTEXT = SimpleNamespace(workspace_id="workspace")


def _install(monkeypatch, renew):
    @contextmanager
    def work(_database):
        yield SimpleNamespace(jobs=SimpleNamespace(renew_lease=renew), commit=lambda: None)

    monkeypatch.setattr(leases, "unit_of_work", work)


def _heartbeat():
    return leases.lease_heartbeat(
        None, CONTEXT, job_id="ab:job:1", worker_id="worker", lease_token="token",
        interval=0.01,
    )


def test_heartbeat_renews_the_short_lease_until_the_block_exits(monkeypatch):
    renewals = []
    renewed_twice = threading.Event()

    def renew(_context, **lease):
        renewals.append(lease)
        if len(renewals) >= 2:
            renewed_twice.set()

    _install(monkeypatch, renew)
    with _heartbeat():
        assert renewed_twice.wait(5.0)
    stopped_at = len(renewals)
    threading.Event().wait(0.05)

    assert len(renewals) == stopped_at  # no renewal after the job finished
    assert renewals[0] == {
        "job_id": "ab:job:1", "worker_id": "worker", "lease_token": "token",
        "lease_seconds": leases.JOB_LEASE_SECONDS,
    }
    assert leases.JOB_LEASE_SECONDS <= 300 < 3600


def test_heartbeat_stops_once_the_lease_is_lost(monkeypatch):
    attempts = []
    lost = threading.Event()

    def renew(_context, **_lease):
        attempts.append(True)
        lost.set()
        raise JobClaimConflict("lease expired")

    _install(monkeypatch, renew)
    with _heartbeat():
        assert lost.wait(5.0)
        threading.Event().wait(0.05)
    assert len(attempts) == 1


def test_heartbeat_retries_after_a_transient_failure(monkeypatch):
    attempts = []
    recovered = threading.Event()

    def renew(_context, **_lease):
        attempts.append(True)
        if len(attempts) == 1:
            raise OSError("connection reset")
        recovered.set()

    _install(monkeypatch, renew)
    with _heartbeat():
        assert recovered.wait(5.0)
