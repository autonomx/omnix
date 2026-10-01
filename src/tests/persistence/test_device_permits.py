from __future__ import annotations

import multiprocessing
import os
import time
import uuid

import pytest

from app.persistence.migrations import discover_migrations
from app.persistence.device_permits import DevicePermitError


def _tenant_values():
    from app.security.tenant_context import local_tenant_context

    context = local_tenant_context()
    return context.user_id, context.workspace_id, context.membership_id, tuple(context.roles)


def _device_permit_process(url, tenant_values, device_id, holder_id, priority, gate, events):
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.device_permits import PostgresDevicePermitService
    from app.runtime.tenant_context import TenantContext
    from app.security.tenant_context import install_process_tenant

    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=4))
    user_id, workspace_id, membership_id, roles = tenant_values
    install_process_tenant(
        TenantContext(
            user_id=user_id,
            workspace_id=workspace_id,
            membership_id=membership_id,
            roles=frozenset(roles),
        )
    )
    service = PostgresDevicePermitService(
        database,
        device_id=device_id,
        lease_seconds=5,
        poll_interval_seconds=0.05,
    )
    try:
        service.configure_capacity("image", capacity=1)
        gate.wait(15)
        lease = service.acquire(
            "image",
            holder_id=holder_id,
            priority=priority,
            timeout_seconds=15,
            lease_seconds=5,
        )
        if lease is None:
            events.put(("timeout", holder_id, time.monotonic()))
            return
        events.put(("acquired", holder_id, time.monotonic()))
        time.sleep(1.0)
        events.put(("released", holder_id, time.monotonic()))
        service.release(lease)
    except BaseException as exc:
        events.put(("error", holder_id, type(exc).__name__, str(exc)))
        raise
    finally:
        database.close()


def _batch_yield_process(url, tenant_values, device_id, events):
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.device_permits import PostgresDevicePermitService
    from app.runtime.tenant_context import TenantContext
    from app.security.tenant_context import install_process_tenant

    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=4))
    user_id, workspace_id, membership_id, roles = tenant_values
    install_process_tenant(
        TenantContext(
            user_id=user_id,
            workspace_id=workspace_id,
            membership_id=membership_id,
            roles=frozenset(roles),
        )
    )
    service = PostgresDevicePermitService(
        database,
        device_id=device_id,
        lease_seconds=5,
        poll_interval_seconds=0.05,
    )
    try:
        service.configure_capacity("tts", capacity=1)
        with service.slot("tts", holder_id="batch-holder", priority="batch", timeout_seconds=10):
            events.put(("batch_active", time.monotonic()))
            deadline = time.monotonic() + 8
            while not service.has_higher_priority_request("tts", priority="batch"):
                if time.monotonic() >= deadline:
                    events.put(("batch_timeout", time.monotonic()))
                    return
                time.sleep(0.02)
        events.put(("batch_yielded", time.monotonic()))
    except BaseException as exc:
        events.put(("batch_error", type(exc).__name__, str(exc)))
        raise
    finally:
        database.close()


def _realtime_permit_process(url, tenant_values, device_id, events, start):
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.device_permits import PostgresDevicePermitService
    from app.runtime.tenant_context import TenantContext
    from app.security.tenant_context import install_process_tenant

    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=4))
    user_id, workspace_id, membership_id, roles = tenant_values
    install_process_tenant(
        TenantContext(
            user_id=user_id,
            workspace_id=workspace_id,
            membership_id=membership_id,
            roles=frozenset(roles),
        )
    )
    service = PostgresDevicePermitService(
        database,
        device_id=device_id,
        lease_seconds=5,
        poll_interval_seconds=0.05,
    )
    try:
        service.configure_capacity("tts", capacity=1)
        if not start.wait(10):
            events.put(("realtime_start_timeout", time.monotonic()))
            return
        with service.slot(
            "tts",
            holder_id="realtime-holder",
            priority="realtime",
            timeout_seconds=8,
        ):
            events.put(("realtime_active", time.monotonic()))
    except BaseException as exc:
        events.put(("realtime_error", type(exc).__name__, str(exc)))
        raise
    finally:
        database.close()


def _hold_expiring_permit_process(url, tenant_values, device_id, events):
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.device_permits import PostgresDevicePermitService
    from app.runtime.tenant_context import TenantContext
    from app.security.tenant_context import install_process_tenant

    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=2))
    user_id, workspace_id, membership_id, roles = tenant_values
    install_process_tenant(
        TenantContext(
            user_id=user_id,
            workspace_id=workspace_id,
            membership_id=membership_id,
            roles=frozenset(roles),
        )
    )
    service = PostgresDevicePermitService(database, device_id=device_id, lease_seconds=5)
    try:
        service.configure_capacity("image", capacity=1)
        lease = service.acquire(
            "image", holder_id="killed-holder", priority="interactive", lease_seconds=5
        )
        events.put(("held" if lease else "not-held", time.monotonic()))
        time.sleep(30)
    finally:
        database.close()


def _cleanup_device(database, device_id: str) -> None:
    from app.persistence.unit_of_work import unit_of_work

    with unit_of_work(database) as work:
        for table in (
            "omnix_device_permits",
            "omnix_device_permit_requests",
            "omnix_device_model_owners",
            "omnix_device_capacity",
        ):
            work.connection.execute(
                f"DELETE FROM {table} WHERE device_id = %s",
                (device_id,),
            )
        work.commit()


def test_device_permit_migration_owns_capacity_requests_leases_and_model_owner():
    migration = next(
        item for item in discover_migrations() if item.version == "0103_device_permits"
    )
    assert migration.phase == "expand" and migration.transactional
    for table in (
        "omnix_device_capacity",
        "omnix_device_permit_requests",
        "omnix_device_permits",
        "omnix_device_model_owners",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration.sql
    assert "idx_omnix_device_permits_active" in migration.sql


@pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="requires disposable PostgreSQL",
)
@pytest.mark.postgres
def test_two_processes_share_capacity_and_diagnostics_show_live_holders():
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.device_permits import PostgresDevicePermitService

    url = os.environ["OMNIX_TEST_DATABASE_URL"]
    tenant_values = _tenant_values()
    device_id = f"permit-test:{uuid.uuid4().hex}"
    context = multiprocessing.get_context("spawn")
    gate = context.Event()
    events = context.Queue()
    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=4))
    service = PostgresDevicePermitService(database, device_id=device_id, lease_seconds=5)
    service.configure_capacity("image", capacity=1)
    service.configure_capacity("tts", capacity=1)
    processes = [
        context.Process(
            target=_device_permit_process,
            args=(url, tenant_values, device_id, f"worker-{index}", "interactive", gate, events),
        )
        for index in range(2)
    ]
    try:
        for process in processes:
            process.start()
        gate.set()
        first_event = events.get(timeout=20)
        assert first_event[0] == "acquired"
        active_diagnostics = {row.model_class: row for row in service.diagnostics()}
        assert active_diagnostics["image"].holders
        assert active_diagnostics["image"].holders[0].holder_id == first_event[1]
        event_rows = [first_event, *(events.get(timeout=20) for _ in range(3))]
        assert all(process.join(timeout=10) is None for process in processes)
        assert all(process.exitcode == 0 for process in processes)
        assert all(row[0] in {"acquired", "released"} for row in event_rows)
        intervals = {}
        for state, holder, timestamp in event_rows:
            intervals.setdefault(holder, {})[state] = timestamp
        assert set(intervals) == {"worker-0", "worker-1"}
        assert all(set(row) == {"acquired", "released"} for row in intervals.values())
        first, second = intervals.values()
        assert first["released"] <= second["acquired"] or second["released"] <= first["acquired"]

        owner = service.hold_model_owner("tts", holder_id="gateway:parent", process_role="gateway")
        try:
            with pytest.raises(DevicePermitError, match="already loaded"):
                service.hold_model_owner(
                    "tts", holder_id="tts-server:duplicate", process_role="tts-server"
                )
            diagnostics = {row.model_class: row for row in service.diagnostics()}
            assert diagnostics["tts"].model_owner is not None
            assert diagnostics["tts"].model_owner[0] == "gateway:parent"
        finally:
            owner.close()
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        _cleanup_device(database, device_id)
        database.close()


@pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="requires disposable PostgreSQL",
)
@pytest.mark.postgres
def test_realtime_request_yields_batch_holder_at_safe_boundary():
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.device_permits import PostgresDevicePermitService

    url = os.environ["OMNIX_TEST_DATABASE_URL"]
    tenant_values = _tenant_values()
    device_id = f"permit-priority-test:{uuid.uuid4().hex}"
    context = multiprocessing.get_context("spawn")
    realtime_start = context.Event()
    events = context.Queue()
    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=4))
    service = PostgresDevicePermitService(database, device_id=device_id, lease_seconds=5)
    service.configure_capacity("tts", capacity=1)
    batch = context.Process(
        target=_batch_yield_process,
        args=(url, tenant_values, device_id, events),
    )
    realtime = context.Process(
        target=_realtime_permit_process,
        args=(url, tenant_values, device_id, events, realtime_start),
    )
    try:
        batch.start()
        batch_active = events.get(timeout=15)
        assert batch_active[0] == "batch_active"
        realtime.start()
        realtime_start.set()
        batch_yielded = events.get(timeout=15)
        realtime_active = events.get(timeout=15)
        assert batch_yielded[0] == "batch_yielded"
        assert realtime_active[0] == "realtime_active"
        assert realtime_active[1] - batch_yielded[1] < 1.5
        batch.join(timeout=10)
        realtime.join(timeout=10)
        assert batch.exitcode == 0 and realtime.exitcode == 0
    finally:
        for process in (batch, realtime):
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        _cleanup_device(database, device_id)
        database.close()


@pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="requires disposable PostgreSQL",
)
@pytest.mark.postgres
def test_killed_permit_holder_is_reclaimed_after_lease_expiry():
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.device_permits import PostgresDevicePermitService

    url = os.environ["OMNIX_TEST_DATABASE_URL"]
    tenant_values = _tenant_values()
    device_id = f"permit-expiry-test:{uuid.uuid4().hex}"
    context = multiprocessing.get_context("spawn")
    events = context.Queue()
    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=3))
    service = PostgresDevicePermitService(database, device_id=device_id, lease_seconds=5)
    service.configure_capacity("image", capacity=1)
    holder = context.Process(
        target=_hold_expiring_permit_process,
        args=(url, tenant_values, device_id, events),
    )
    try:
        holder.start()
        assert events.get(timeout=15)[0] == "held"
        holder.terminate()
        holder.join(timeout=5)
        time.sleep(5.2)
        reclaimed = service.acquire(
            "image",
            holder_id="reclaimer",
            priority="interactive",
            timeout_seconds=3,
            lease_seconds=5,
        )
        assert reclaimed is not None
        assert service.release(reclaimed)
    finally:
        if holder.is_alive():
            holder.terminate()
            holder.join(timeout=5)
        _cleanup_device(database, device_id)
        database.close()


@pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="requires disposable PostgreSQL",
)
@pytest.mark.postgres
def test_live_fake_tts_load_scales_with_device_capacity_and_returns_429(monkeypatch):
    import json
    import secrets
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.device_permits import PostgresDevicePermitService
    from app.runtime.tenant_context import TenantContext
    from app.security.service_token import service_headers
    from app.security.tenant_context import install_process_tenant

    import tts_server

    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", secrets.token_urlsafe(32))
    monkeypatch.setenv("OMNIX_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
    database = PostgresDatabase(
        DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=10)
    )
    user_id, workspace_id, membership_id, roles = _tenant_values()
    tenant = TenantContext(
        user_id=user_id,
        workspace_id=workspace_id,
        membership_id=membership_id,
        roles=frozenset(roles),
    )
    device_ids: list[str] = []
    cases: list[dict[str, object]] = []

    class FakeTTS:
        sample_rate = 24_000

        def __init__(self):
            self.release = threading.Event()
            self.changed = threading.Condition()
            self.active = 0
            self.peak_active = 0

        def generate_audio_stream(self, **_kwargs):
            with self.changed:
                self.active += 1
                self.peak_active = max(self.peak_active, self.active)
                self.changed.notify_all()
            try:
                if not self.release.wait(5):
                    raise TimeoutError("FakeTTS release gate timed out")
                yield [0.25, -0.25], self.sample_rate, {}
            finally:
                with self.changed:
                    self.active -= 1
                    self.changed.notify_all()

        def wait_for_active(self, target: int, timeout: float) -> bool:
            with self.changed:
                return self.changed.wait_for(lambda: self.active >= target, timeout)

    try:
        monkeypatch.setattr(tts_server, "_TTS_PROVIDER_ERROR", "")
        headers = service_headers()
        request_count = 4
        for capacity in (1, 2):
            device_id = f"live-call-fake-tts:{uuid.uuid4().hex}"
            device_ids.append(device_id)
            service = PostgresDevicePermitService(
                database,
                device_id=device_id,
                lease_seconds=5,
                poll_interval_seconds=0.03,
            )
            service.configure_capacity("tts", capacity=capacity, realtime_reserved_units=0)
            fake_tts = FakeTTS()
            monkeypatch.setattr(tts_server, "_TTS_PROVIDER", fake_tts)

            def permit_slot(model_class, *, priority, timeout_seconds):
                return service.slot(
                    model_class,
                    holder_id=f"fake-live-call:{uuid.uuid4().hex}",
                    priority=priority,
                    timeout_seconds=timeout_seconds,
                )

            monkeypatch.setattr(tts_server, "device_permit_slot", permit_slot)

            def issue_request() -> dict[str, object]:
                install_process_tenant(tenant)
                client = TestClient(
                    tts_server.app,
                    base_url="http://127.0.0.1",
                    headers=headers,
                )
                started = time.perf_counter()
                response = client.post(
                    "/api/tts/live-call/stream",
                    json={"text": "capacity probe", "speaker": "default", "language": "en"},
                )
                return {
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "retry_after": response.headers.get("retry-after"),
                }

            with ThreadPoolExecutor(max_workers=request_count) as executor:
                futures = [executor.submit(issue_request) for _ in range(request_count)]
                assert fake_tts.wait_for_active(capacity, timeout=5), (
                    f"FakeTTS did not reach configured capacity {capacity}"
                )
                deadline = time.monotonic() + 5
                while True:
                    diagnostic = service.diagnostics()[0]
                    queued = sum(count for _priority, count in diagnostic.waiting)
                    if len(diagnostic.holders) == capacity and queued >= request_count - capacity:
                        break
                    if time.monotonic() >= deadline:
                        pytest.fail(
                            f"expected {request_count - capacity} queued calls at capacity {capacity}"
                        )
                    time.sleep(0.05)
                time.sleep(1.2)
                fake_tts.release.set()
                outcomes = [future.result(timeout=10) for future in futures]

            statuses = [int(row["status"]) for row in outcomes]
            accepted = statuses.count(200)
            overloaded = statuses.count(429)
            assert accepted == capacity
            assert overloaded == request_count - capacity
            assert fake_tts.peak_active == capacity
            assert all(row["retry_after"] == "1" for row in outcomes if row["status"] == 429)
            cases.append({
                "capacity_units": capacity,
                "concurrent_requests": request_count,
                "accepted_calls": accepted,
                "peak_active_calls": fake_tts.peak_active,
                "overload_429": overloaded,
                "request_durations_ms": [row["duration_ms"] for row in outcomes],
            })
    finally:
        for device_id in device_ids:
            _cleanup_device(database, device_id)
        database.close()

    assert cases[1]["accepted_calls"] == 2 * cases[0]["accepted_calls"]
    report = {
        "measurement": "live-call-fake-tts-capacity",
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": os.environ.get("GITHUB_SHA", "working-tree"),
        "result": "passed",
        "cases": cases,
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(f"LIVE_CALL_CAPACITY_MEASUREMENT={json.dumps(report, sort_keys=True)}")
    artifact_path = os.environ.get("OMNIX_LIVE_CALL_MEASUREMENT_PATH")
    if artifact_path:
        path = Path(artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
