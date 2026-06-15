"""Contract tests for the shared gateway job API."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _client(db_path: Path) -> TestClient:
    from app.gateway.main import create_gateway_app
    from app.jobs import SQLiteJobStore

    return TestClient(
        create_gateway_app(job_store_factory=lambda: SQLiteJobStore(db_path)),
        raise_server_exceptions=False,
    )


def _create_job(
    client: TestClient,
    *,
    module: str = "image",
    job_type: str = "image.generate",
    resource_class: str = "gpu:image",
    priority: int = 0,
) -> dict:
    response = client.post(
        "/api/jobs",
        json={
            "module": module,
            "type": job_type,
            "resource_class": resource_class,
            "priority": priority,
            "input_payload": {"prompt": "tiny smoke test"},
        },
    )
    assert response.status_code == 200
    return response.json()


def test_gateway_jobs_are_durable_across_clients(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.sqlite"
    client = _client(db_path)

    created = _create_job(client, priority=3)

    next_client = _client(db_path)
    response = next_client.get(f"/api/jobs/{created['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == created["id"]
    assert payload["status"] == "queued"
    assert payload["resource_class"] == "gpu:image"
    assert payload["stages"][0]["id"] == "run"


def test_scheduler_enforces_single_gpu_lock_and_network_bypass(tmp_path: Path) -> None:
    client = _client(tmp_path / "jobs.sqlite")
    gpu_image = _create_job(client, resource_class="gpu:image", priority=10)
    gpu_tts = _create_job(
        client,
        module="voice",
        job_type="tts.synthesize",
        resource_class="gpu:tts",
        priority=9,
    )
    network = _create_job(client, module="chatbot", job_type="chat.remote", resource_class="network", priority=8)

    first = client.post("/api/jobs/claim", json={"worker_id": "worker:gpu"})
    assert first.status_code == 200
    assert first.json()["job"]["id"] == gpu_image["id"]

    second = client.post("/api/jobs/claim", json={"worker_id": "worker:network"})
    assert second.status_code == 200
    assert second.json()["job"]["id"] == network["id"]

    completed = client.post(f"/api/jobs/{gpu_image['id']}/complete", json={})
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"

    third = client.post("/api/jobs/claim", json={"worker_id": "worker:gpu"})
    assert third.status_code == 200
    assert third.json()["job"]["id"] == gpu_tts["id"]


def test_cancel_pending_job_is_terminal(tmp_path: Path) -> None:
    client = _client(tmp_path / "jobs.sqlite")
    created = _create_job(client)

    response = client.post(f"/api/jobs/{created['id']}/cancel", json={"reason": "user_request"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "canceled"
    assert payload["cancel"]["requested"] is True
    assert payload["cancel"]["acknowledged_at"]


def test_cancel_running_job_is_observable_without_orphaning_lease(tmp_path: Path) -> None:
    client = _client(tmp_path / "jobs.sqlite")
    created = _create_job(client)

    claim = client.post("/api/jobs/claim", json={"worker_id": "worker:gpu"})
    assert claim.status_code == 200
    assert claim.json()["job"]["id"] == created["id"]

    canceled = client.post(f"/api/jobs/{created['id']}/cancel", json={"reason": "release_readiness"})
    assert canceled.status_code == 200
    payload = canceled.json()
    assert payload["status"] == "cancel_requested"
    assert payload["cancel"]["requested"] is True
    assert payload["cancel"]["acknowledged_at"] is None
    assert payload["lease"]["worker_id"] == "worker:gpu"

    events = client.get("/api/jobs/events")
    assert events.status_code == 200
    assert "event: job.updated" in events.text
    assert "cancel_requested" in events.text
    assert "release_readiness" in events.text


def test_failed_job_surfaces_diagnostics_and_terminal_event(tmp_path: Path) -> None:
    client = _client(tmp_path / "jobs.sqlite")
    created = _create_job(client, module="diagnostics", job_type="diagnostics.fail", resource_class="cpu")

    response = client.post(
        f"/api/jobs/{created['id']}/fail",
        json={
            "code": "provider_timeout",
            "message": "Provider timed out during release-readiness smoke test.",
            "retryable": True,
            "details": {"provider": "mock-llm", "timeout_ms": 250},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["error"] == {
        "code": "provider_timeout",
        "message": "Provider timed out during release-readiness smoke test.",
        "retryable": True,
        "details": {"provider": "mock-llm", "timeout_ms": 250},
    }
    assert payload["completed_at"]
    assert payload["lease"] is None

    events = client.get("/api/jobs/events")
    assert events.status_code == 200
    assert "event: job.failed" in events.text
    assert "provider_timeout" in events.text


def test_job_events_are_named_sse_events(tmp_path: Path) -> None:
    client = _client(tmp_path / "jobs.sqlite")
    created = _create_job(client)

    response = client.get("/api/jobs/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: job.created" in response.text
    assert created["id"] in response.text


def test_tts_adapter_preserves_legacy_queue_id(tmp_path: Path) -> None:
    from app.jobs import SQLiteJobStore, enqueue_tts_job

    class FakeTTSQueue:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def enqueue(self, text, speaker=None, voice_id=None, chunk_index=-1, **kwargs):
            self.calls.append(
                {
                    "text": text,
                    "speaker": speaker,
                    "voice_id": voice_id,
                    "chunk_index": chunk_index,
                    "kwargs": kwargs,
                }
            )
            return "legacy-tts-1"

    queue = FakeTTSQueue()
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")

    job = enqueue_tts_job(
        store,
        queue,
        text="hello",
        speaker="narrator",
        chunk_index=2,
        priority=4,
        speed=1.0,
    )

    assert queue.calls == [
        {
            "text": "hello",
            "speaker": "narrator",
            "voice_id": None,
            "chunk_index": 2,
            "kwargs": {"speed": 1.0},
        }
    ]
    assert job.type == "tts.synthesize"
    assert job.resource_class == "gpu:tts"
    assert job.compat["legacy_job_id"] == "legacy-tts-1"
    assert [stage.id for stage in job.stages] == ["chunk:0002", "reassemble"]


@pytest.mark.asyncio
async def test_local_executor_completes_registered_handler(tmp_path: Path) -> None:
    from app.jobs import (
        CreateJobRequest,
        LocalJobExecutor,
        ResourceClass,
        SQLiteJobStore,
    )

    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    created = store.create_job(
        CreateJobRequest(
            module="diagnostics",
            type="diagnostics.echo",
            resource_class=ResourceClass.CPU,
            input_payload={"message": "ok"},
        )
    )

    async def handler(job):
        return {
            "logs": [{"level": "info", "message": job.input_payload["message"]}],
            "output_refs": [{"kind": "diagnostic", "id": "echo"}],
        }

    result = await LocalJobExecutor(store, {"diagnostics.echo": handler}).run_once()

    assert result is not None
    assert result.id == created.id
    assert result.status == "completed"
    assert result.output_refs == [{"kind": "diagnostic", "id": "echo"}]
    assert result.logs == [{"level": "info", "message": "ok"}]
