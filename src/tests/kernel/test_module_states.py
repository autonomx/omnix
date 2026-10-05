"""Module lifecycle state: draining and retired modules take no new work (ADR-0016, PA-4.3)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.composition.gateway.feature_registry import feature_guard
from app.jobs.handlers import JobExecutionContext, JobHandlerRegistry, JobHandlerSpec, executing_job
from app.jobs.models import JobRecord
from app.persistence.module_states import ModuleState

NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def test_only_an_active_module_takes_new_work_and_a_draining_one_takes_follow_ups_until_its_deadline() -> None:
    assert ModuleState("m").accepts_new_work and ModuleState("m").accepts_follow_up(NOW)
    draining = ModuleState("m", state="draining", drain_deadline=NOW + timedelta(minutes=5))
    assert not draining.accepts_new_work
    assert draining.accepts_follow_up(NOW)
    assert not draining.accepts_follow_up(NOW + timedelta(minutes=6))
    retired = ModuleState("m", state="retired")
    assert not retired.accepts_new_work and not retired.accepts_follow_up(NOW)


def test_the_registry_knows_each_types_module_and_the_job_a_handler_runs() -> None:
    seen = []

    def handler(_context: JobExecutionContext, job: JobRecord) -> JobRecord:
        seen.append(executing_job())
        return job

    registry = JobHandlerRegistry()
    registry.register(JobHandlerSpec(type="sample.work", handler=handler), owner="sample")
    job = JobRecord(id="job-1", module="sample", type="sample.work", status="running", resource_class="cpu",
                    created_at=NOW.isoformat(), updated_at=NOW.isoformat())

    registry.execute(JobExecutionContext(job_store=None), job)

    assert registry.owner("sample.work") == "sample" and registry.owner("other.work") is None
    assert seen == [("job-1", "sample.work")]
    assert executing_job() is None


@pytest.mark.parametrize(("state", "read", "write"), [
    ("active", 200, 200),
    ("draining", 200, 503),
    ("retired", 503, 503),
])
def test_a_modules_routes_follow_its_state(monkeypatch, state: str, read: int, write: int) -> None:
    monkeypatch.setattr("app.persistence.module_states.cached_module_state",
                        lambda module_id: ModuleState(module_id, state=state))
    router = APIRouter()
    router.add_api_route("/sample", lambda: {"ok": True}, methods=["GET"])
    router.add_api_route("/sample", lambda: {"ok": True}, methods=["POST"])
    app = FastAPI()
    app.include_router(router, dependencies=[Depends(feature_guard("sample"))])
    client = TestClient(app)

    assert client.get("/sample").status_code == read
    response = client.post("/sample")
    assert response.status_code == write
    if write == 503:
        assert response.headers["retry-after"] == "30"
