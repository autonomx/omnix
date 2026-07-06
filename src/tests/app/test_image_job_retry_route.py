from __future__ import annotations

from fastapi.testclient import TestClient

import app.gateway.image_workspace_routes as image_workspace_routes
from app.gateway.main import create_gateway_app
from app.jobs import CreateJobRequest, FailJobRequest, ResourceClass, SQLiteJobStore


def test_failed_image_job_can_be_retried(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    source = store.create_job(
        CreateJobRequest(
            module="image-generation",
            type="image.generate",
            resource_class=ResourceClass.GPU_IMAGE,
            input_payload={"prompt": "Retry this image", "width": 768, "height": 768},
            compat={"contract": "image_generation_asset_v1"},
        )
    )
    store.fail_job(source.id, FailJobRequest(message="provider failed", retryable=True))
    monkeypatch.setattr(image_workspace_routes, "default_job_store", lambda: store)
    client = TestClient(create_gateway_app())

    response = client.post(f"/api/image-generation/jobs/{source.id}/retry")

    assert response.status_code == 200
    retried = response.json()
    assert retried["id"] != source.id
    assert retried["status"] == "queued"
    assert retried["input_payload"]["prompt"] == "Retry this image"
    assert retried["compat"]["retry_of"] == source.id


def test_active_image_job_cannot_be_retried(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    source = store.create_job(
        CreateJobRequest(
            module="image-generation",
            type="image.generate",
            resource_class=ResourceClass.GPU_IMAGE,
            input_payload={"prompt": "Still queued", "width": 768, "height": 768},
        )
    )
    monkeypatch.setattr(image_workspace_routes, "default_job_store", lambda: store)
    client = TestClient(create_gateway_app())

    response = client.post(f"/api/image-generation/jobs/{source.id}/retry")

    assert response.status_code == 409
    assert response.json()["detail"] == "job_not_retryable"
