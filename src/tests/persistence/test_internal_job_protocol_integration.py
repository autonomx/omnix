from __future__ import annotations

import os
import secrets
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.core_jobs_routes import register_core_jobs_routes
from app.jobs.durable_feature_worker import _AuthorityBoundJobStore
from app.jobs.foreground_execution import ForegroundExecution, current_foreground_execution, foreground_execution
from app.jobs.models import CompleteJobRequest, CreateJobRequest, FailJobRequest, ResourceClass
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.execution_repositories import JobClaimConflict
from app.persistence.job_runtime_compat import PostgresJobStoreAdapter
from app.persistence.repositories import PostgresIdentityRepository
from app.persistence.unit_of_work import unit_of_work

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest.fixture
def client(monkeypatch):
    url = os.environ["OMNIX_TEST_DATABASE_URL"]
    assert urlsplit(url).path in {"/omnix_test", "/omnix_refactor_baseline"}
    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=4))
    store = PostgresJobStoreAdapter(database)
    workspace = f"workspace:internal-jobs:{secrets.token_urlsafe(12)}"
    with database.transaction() as connection:
        connection.execute("INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, 'Worker protocol test', %s)", (workspace, store.context.user_id))
        connection.execute("INSERT INTO omnix_workspace_memberships (id, workspace_id, user_id, roles) VALUES (%s, %s, %s, %s)", (secrets.token_urlsafe(12), workspace, store.context.user_id, ["owner", "admin", "member"]))
        store.context = PostgresIdentityRepository(connection).load_context(user_id=store.context.user_id, workspace_id=workspace)
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", token)
    app = FastAPI()
    register_core_jobs_routes(app, get_job_store=lambda: store, get_chat_store=lambda: None)
    try:
        with TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"}) as http:
            http.store = store
            http.token = token
            yield http
    finally:
        database.close()


def _job(client):
    return client.store.create_job(CreateJobRequest(module="diagnostics", type="diagnostics.fencing", resource_class=ResourceClass.CPU))


def _claim(client, worker="worker:first"):
    response = client.post("/internal/jobs/claim", json={"worker_id": worker, "resource_classes": ["cpu"]}, headers={"X-Omnix-Service-Token": client.token})
    assert response.status_code == 200, response.text
    assert response.json()["ok"]
    return response.json()["job"]


def _credentials(claim):
    return {"worker_id": claim["lease"]["worker_id"], "lease_token": claim["lease"]["token"]}


@pytest.mark.parametrize("path", ["claim", "job-one/complete", "job-one/fail"])
def test_worker_protocol_requires_service_token(client, path):
    response = client.post(f"/internal/jobs/{path}", json={})
    assert response.status_code == 401
    assert "Traceback" not in response.text


@pytest.mark.parametrize("path", ["claim", "job-one/complete", "job-one/fail"])
def test_retired_public_worker_paths_are_gone(client, path, caplog):
    response = client.post(f"/api/jobs/{path}", json={})
    assert response.status_code == 410
    assert "Retired public job worker endpoint" in caplog.text


@pytest.mark.parametrize("operation", ["complete", "fail"])
def test_active_lease_requires_callers_exact_credentials(client, operation):
    job = _job(client)
    claim = _claim(client)
    assert claim["id"] == job.id
    extra = {"message": "Failed"} if operation == "fail" else {}
    headers = {"X-Omnix-Service-Token": client.token}
    endpoint = f"/internal/jobs/{job.id}/{operation}"
    assert client.post(endpoint, json=extra, headers=headers).status_code == 422
    assert client.post(endpoint, json={**_credentials(claim), **extra, "lease_token": "wrong-token"}, headers=headers).status_code == 409
    assert client.post(endpoint, json={**_credentials(claim), **extra, "worker_id": "wrong-worker"}, headers=headers).status_code == 409
    assert client.store.get_job(job.id).status.value == "leased"
    response = client.post(endpoint, json={**_credentials(claim), **extra}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == ("completed" if operation == "complete" else "failed")


@pytest.mark.parametrize("operation", ["complete", "fail"])
def test_stale_attempt_cannot_borrow_successors_lease(client, operation):
    job = _job(client)
    first = _claim(client)
    with client.store.database.transaction() as connection:
        connection.execute("UPDATE omnix_jobs SET lease_expires_at = clock_timestamp() - INTERVAL '1 second' WHERE id = %s", (job.id,))
    second = _claim(client, "worker:successor")
    assert second["id"] == first["id"]
    assert second["lease"]["token"] != first["lease"]["token"]
    model = FailJobRequest if operation == "fail" else CompleteJobRequest
    extra = {"message": "Failed"} if operation == "fail" else {}
    with pytest.raises(JobClaimConflict):
        getattr(client.store, f"{operation}_job")(job.id, model(**_credentials(first), **extra))
    with pytest.raises(JobClaimConflict):
        getattr(client.store, f"{operation}_job")(job.id, model(**extra))
    assert client.store.get_job(job.id).lease.token == second["lease"]["token"]


@pytest.mark.parametrize("operation", ["complete", "fail"])
def test_durable_executor_passes_originally_claimed_credentials(client, operation):
    job = _job(client)
    _claim(client)
    claimed = client.store.get_job(job.id)
    bound = _AuthorityBoundJobStore(client.store, SimpleNamespace(require_live=lambda: None), claimed)
    model = FailJobRequest if operation == "fail" else CompleteJobRequest
    request = model(**({"message": "Failed"} if operation == "fail" else {}))
    result = getattr(bound, f"{operation}_job")(job.id, request)
    assert result.status.value == ("completed" if operation == "complete" else "failed")


def test_bound_executor_cannot_finalize_a_different_job(client):
    job = _job(client)
    _claim(client)
    bound = _AuthorityBoundJobStore(client.store, SimpleNamespace(require_live=lambda: None), client.store.get_job(job.id))
    with pytest.raises(JobClaimConflict, match="another job"):
        bound.complete_job("other-job", CompleteJobRequest())


def test_local_executor_keeps_claim_credentials(client):
    import asyncio
    from app.jobs.executor import LocalJobExecutor
    job = _job(client)
    executor = LocalJobExecutor(client.store, {"diagnostics.fencing": lambda _: {"output_refs": [{"done": True}]}})
    completed = asyncio.run(executor.run_once([ResourceClass.CPU]))
    assert completed.id == job.id
    assert completed.status.value == "completed"


@pytest.mark.parametrize("operation", ["complete", "fail"])
def test_expiry_is_checked_at_finalization_not_transaction_start(client, operation):
    job = _job(client)
    claim = _claim(client)
    with unit_of_work(client.store.database) as work:
        # Expire the lease after this transaction began. No sleep or timing
        # threshold: the stored expiry is already past before finalization.
        row = work.connection.execute(
            "UPDATE omnix_jobs SET lease_expires_at = clock_timestamp() "
            "WHERE id = %s RETURNING lease_expires_at > CURRENT_TIMESTAMP",
            (job.id,),
        ).fetchone()
        assert row[0] is True
        arguments = {"output_refs": []} if operation == "complete" else {"error": {"message": "Failed", "retryable": False}}
        with pytest.raises(JobClaimConflict):
            getattr(work.jobs, operation)(client.store.context, job_id=job.id, **_credentials(claim), **arguments)
        work.rollback()


@pytest.mark.parametrize("marker", ["record_only", "inline_execution", "execution_owner"])
def test_public_job_creation_cannot_select_execution_authority(client, marker):
    response = client.post("/api/jobs", json={
        "module": "diagnostics", "type": "diagnostics.fencing",
        "resource_class": "cpu", "compat": {marker: True},
    })
    assert response.status_code == 422
    assert client.store.list_jobs() == []


@pytest.mark.parametrize("operation", ["mark_record_only_running", "complete_record_only", "fail_record_only"])
@pytest.mark.parametrize("marker", ["record_only", "inline_execution"])
def test_generic_marker_cannot_authorize_unleased_repository_transition(client, operation, marker):
    job = client.store.create_job(CreateJobRequest(
        module="diagnostics", type="diagnostics.fencing", resource_class=ResourceClass.CPU,
        compat={marker: True},
    ))
    arguments = {"output_refs": []} if operation == "complete_record_only" else (
        {"error": {"message": "failed"}} if operation == "fail_record_only" else {}
    )
    with unit_of_work(client.store.database) as work:
        with pytest.raises(JobClaimConflict):
            getattr(work.jobs, operation)(client.store.context, job_id=job.id, **arguments)
        work.rollback()
    assert client.store.get_job(job.id).status.value == "queued"


@pytest.mark.parametrize("operation", ["complete", "fail"])
def test_ownerless_chat_cannot_finalize_without_lease(client, operation):
    job = client.store.create_job(CreateJobRequest(
        module="chatbot", type="chat.generate", resource_class=ResourceClass.CPU,
        compat={"inline_execution": True},
    ))
    request = CompleteJobRequest() if operation == "complete" else FailJobRequest(message="failed")
    with pytest.raises(JobClaimConflict):
        getattr(client.store, f"{operation}_job")(job.id, request)
    assert client.store.get_job(job.id).status.value == "queued"


def _foreground_job(client):
    session_id = "session:foreground"
    submission_id = secrets.token_urlsafe(12)
    job = client.store.create_job(CreateJobRequest(
        module="rpg", type="rpg.turn.foreground_record", resource_class=ResourceClass.CPU,
        input_ref={"session_id": session_id}, input_payload={"submission_id": submission_id},
        compat={"record_only": True},
    ))
    with unit_of_work(client.store.database) as work:
        claim = work.foreground_submissions.claim(
            client.store.context, session_id=session_id, submission_id=submission_id,
        )
        assert work.foreground_submissions.attach_job(
            client.store.context, session_id=session_id, submission_id=submission_id,
            claim_token=claim["claim_token"], job_id=job.id,
        )
        assert work.foreground_submissions.start_execution(
            client.store.context, session_id=session_id, submission_id=submission_id,
            claim_token=claim["claim_token"],
        )
        work.commit()
    return job, ForegroundExecution(
        client.store.context.workspace_id, session_id, submission_id, job.id, claim["claim_token"],
    )


@pytest.mark.parametrize("operation", ["complete", "fail"])
def test_foreground_finalization_requires_original_scoped_claim(client, operation):
    from dataclasses import replace

    job, execution = _foreground_job(client)
    request = CompleteJobRequest() if operation == "complete" else FailJobRequest(message="failed")
    assert current_foreground_execution() is None
    with pytest.raises(JobClaimConflict):
        getattr(client.store, f"{operation}_job")(job.id, request)
    with foreground_execution(replace(execution, claim_token="wrong-claim")):
        with pytest.raises(JobClaimConflict):
            getattr(client.store, f"{operation}_job")(job.id, request)
    with foreground_execution(execution):
        assert client.store.mark_running(job.id).status.value == "running"
        assert getattr(client.store, f"{operation}_job")(job.id, request).status.value == (
            "completed" if operation == "complete" else "failed"
        )
    assert current_foreground_execution() is None


@pytest.mark.parametrize("operation", ["complete_record_only", "fail_record_only"])
def test_foreground_repository_cannot_bypass_worker_lease(client, operation):
    job, execution = _foreground_job(client)
    arguments = {"output_refs": []} if operation == "complete_record_only" else {"error": {"message": "failed"}}
    with unit_of_work(client.store.database) as work:
        # Simulate a legacy/corrupt row: the foreground path must never clear or
        # ignore a worker lease, including an already expired one.
        work.connection.execute(
            "UPDATE omnix_jobs SET status = 'running', lease_owner = 'worker:legacy', "
            "lease_token = 'legacy-token', lease_expires_at = clock_timestamp() - INTERVAL '1 second' "
            "WHERE id = %s", (job.id,),
        )
        with pytest.raises(JobClaimConflict):
            getattr(work.jobs, operation)(
                client.store.context, job_id=job.id,
                submission_claim_token=execution.claim_token, **arguments,
            )
        work.rollback()


def test_foreground_records_are_never_claimed_by_generic_workers(client):
    job, _ = _foreground_job(client)
    response = client.post("/internal/jobs/claim", json={
        "worker_id": "worker:generic", "resource_classes": ["cpu"],
    }, headers={"X-Omnix-Service-Token": client.token})
    assert response.status_code == 200
    assert response.json()["job"] is None
    assert client.store.get_job(job.id).status.value == "queued"


@pytest.mark.parametrize("job_type", ["chat.generate", "rpg.turn.foreground_record"])
def test_public_jobs_cannot_create_foreground_execution_records(client, job_type):
    response = client.post("/api/jobs", json={
        "module": "rpg", "type": job_type, "resource_class": "cpu",
    })
    assert response.status_code == 422
    assert client.store.list_jobs() == []


def test_public_jobs_still_admit_leased_feature_work(client):
    response = client.post("/api/jobs", json={
        "module": "diagnostics", "type": "diagnostics.fencing", "resource_class": "cpu",
        "compat": {"source": "feature_ui"},
    })
    assert response.status_code == 200
    assert _claim(client)["id"] == response.json()["id"]


@pytest.mark.parametrize("field", ["workspace_id", "session_id", "submission_id", "job_id"])
def test_foreground_scope_is_bound_to_exact_job_and_workspace(client, field):
    from dataclasses import replace

    job, execution = _foreground_job(client)
    with foreground_execution(replace(execution, **{field: "different-subject"})):
        with pytest.raises(JobClaimConflict, match="another job"):
            client.store.complete_job(job.id, CompleteJobRequest())
    assert current_foreground_execution() is None
    assert client.store.get_job(job.id).status.value == "queued"


@pytest.mark.parametrize("operation", ["mark_record_only_running", "complete_record_only", "fail_record_only"])
def test_foreground_repository_requires_execution_to_have_started(client, operation):
    job, execution = _foreground_job(client)
    arguments = {"output_refs": []} if operation == "complete_record_only" else (
        {"error": {"message": "failed"}} if operation == "fail_record_only" else {}
    )
    with unit_of_work(client.store.database) as work:
        work.connection.execute(
            "UPDATE omnix_rpg_foreground_submissions SET execution_started_at = NULL "
            "WHERE workspace_id = %s AND session_id = %s AND submission_id = %s",
            (execution.workspace_id, execution.session_id, execution.submission_id),
        )
        with pytest.raises(JobClaimConflict):
            getattr(work.jobs, operation)(client.store.context, job_id=job.id,
                submission_claim_token=execution.claim_token, **arguments)
        work.rollback()
