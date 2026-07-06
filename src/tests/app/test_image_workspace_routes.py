from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assets import AssetRecord, AssetType
from app.assets.store import SharedAssetStore
import app.gateway.image_workspace_routes as image_workspace_routes
from app.jobs import CreateJobRequest, ResourceClass, SQLiteJobStore


def test_image_workspace_routes_are_filtered_and_bounded(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    jobs = SQLiteJobStore(tmp_path / "jobs.sqlite")
    jobs.create_job(
        CreateJobRequest(
            module="image-generation",
            type="image.generate",
            resource_class=ResourceClass.GPU_IMAGE,
            input_payload={"prompt": "one"},
        )
    )
    jobs.create_job(
        CreateJobRequest(
            module="voice",
            type="tts.synthesize",
            resource_class=ResourceClass.GPU_TTS,
            input_payload={"text": "not an image"},
        )
    )

    assets = SharedAssetStore(tmp_path / "assets.json")
    assets.upsert_asset(
        AssetRecord(
            id="image:one",
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path="one.png",
            created_at="2026-01-02T00:00:00+00:00",
        )
    )
    assets.upsert_asset(
        AssetRecord(
            id="audio:one",
            module="voice",
            type=AssetType.AUDIO,
            mime_type="audio/wav",
            storage_path="one.wav",
            created_at="2026-01-03T00:00:00+00:00",
        )
    )

    monkeypatch.setattr(image_workspace_routes, "default_job_store", lambda: jobs)
    monkeypatch.setattr(image_workspace_routes, "default_asset_store", lambda: assets)
    app = FastAPI()
    image_workspace_routes.register_image_workspace_routes(app)
    client = TestClient(app)

    job_response = client.get("/api/image-generation/jobs?limit=1")
    asset_response = client.get("/api/image-generation/assets?limit=1")

    assert job_response.status_code == 200
    assert [job["type"] for job in job_response.json()["jobs"]] == ["image.generate"]
    assert asset_response.status_code == 200
    assert [asset["id"] for asset in asset_response.json()["assets"]] == ["image:one"]


def test_image_workspace_jobs_tolerates_store_read_failure(monkeypatch) -> None:
    class BrokenStore:
        def list_jobs(self) -> list[object]:
            raise OSError("transient disk read failure")

    monkeypatch.setattr(image_workspace_routes, "default_job_store", BrokenStore)
    app = FastAPI()
    image_workspace_routes.register_image_workspace_routes(app)
    client = TestClient(app)

    response = client.get("/api/image-generation/jobs")

    assert response.status_code == 200
    assert response.json()["jobs"] == []
