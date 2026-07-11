from __future__ import annotations

import time
from pathlib import Path

from app.image.models import ImageGenerationResponse
from app.jobs import CreateJobRequest, ResourceClass, SQLiteJobStore
from app.jobs.models import JobStage
from app.jobs.image_inline import execute_image_job


class MemoryAssetStore:
    def __init__(self) -> None:
        self.assets = []

    def upsert_asset(self, asset):
        self.assets.append(asset)
        return asset


def test_image_job_executes_and_persists_shared_asset(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    monkeypatch.setattr(Path, "is_file", lambda _path: True)
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    asset_store = MemoryAssetStore()
    job = job_store.create_job(
        CreateJobRequest(
            module="image-generation",
            type="image.generate",
            resource_class=ResourceClass.GPU_IMAGE,
            input_payload={
                "prompt": "A luminous mountain lake",
                "provider_id": "image:mock",
                "width": 768,
                "height": 768,
            },
        )
    )

    completed = execute_image_job(
        job_store,
        job,
        asset_store=asset_store,
        generate_fn=lambda payload: ImageGenerationResponse(
            ok=True,
            provider=payload["provider"],
            status="completed",
            local_path="result.png",
            width=payload["width"],
            height=payload["height"],
        ),
    )

    assert completed.status.value == "completed"
    output_ref = completed.output_refs[0]
    assert output_ref["asset_id"].startswith("image:image-generation-")
    assert output_ref["title"] == "A luminous mountain lake"
    assert "storage_path" not in output_ref
    assert len(asset_store.assets) == 1
    assert asset_store.assets[0].source_job_id == job.id
    assert asset_store.assets[0].metadata["provider_key"] == "mock"
    assert asset_store.assets[0].metadata["source_module"] == "image-generation"


def test_character_avatar_image_keeps_its_module_boundary(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    monkeypatch.setattr(Path, "is_file", lambda _path: True)
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    asset_store = MemoryAssetStore()
    job = job_store.create_job(
        CreateJobRequest(
            module="character-avatar",
            type="image.generate",
            resource_class=ResourceClass.GPU_IMAGE,
            input_payload={
                "prompt": "A locked avatar frame",
                "provider_id": "image:mock",
                "width": 768,
                "height": 768,
                "metadata": {"character_id": "maya", "avatar_variant": "mouth_small"},
            },
        )
    )

    completed = execute_image_job(
        job_store,
        job,
        asset_store=asset_store,
        generate_fn=lambda payload: ImageGenerationResponse(
            ok=True,
            provider=payload["provider"],
            status="completed",
            local_path="avatar.png",
            width=payload["width"],
            height=payload["height"],
        ),
    )

    assert completed.status.value == "completed"
    assert asset_store.assets[0].module == "character-avatar"
    assert asset_store.assets[0].metadata["source_module"] == "character-avatar"


def test_image_job_reports_milestone_progress_during_generation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    monkeypatch.setattr(Path, "is_file", lambda _path: True)
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    asset_store = MemoryAssetStore()
    job = job_store.create_job(
        CreateJobRequest(
            module="image-generation",
            type="image.generate",
            resource_class=ResourceClass.GPU_IMAGE,
            stages=[
                JobStage(id="generate-image", label="Generate image", resource_class=ResourceClass.GPU_IMAGE),
                JobStage(id="store-asset", label="Store image asset", resource_class=ResourceClass.CPU),
            ],
            input_payload={
                "prompt": "A luminous mountain lake",
                "provider_id": "image:mock",
                "width": 768,
                "height": 768,
            },
        )
    )

    def generate(payload):
        running = job_store.get_job(job.id)
        assert running is not None
        assert running.progress.current == 0
        assert running.progress.total == 100
        assert running.progress.message == "Generating image - 0%"
        assert running.stages[0].status.value == "running"
        assert payload["request_id"] == job.id
        return ImageGenerationResponse(
            ok=True,
            provider=payload["provider"],
            status="completed",
            local_path="result.png",
            width=payload["width"],
            height=payload["height"],
        )

    completed = execute_image_job(job_store, job, asset_store=asset_store, generate_fn=generate)

    assert completed.status.value == "completed"
    assert completed.progress.message == "completed"


def test_image_job_polls_service_step_progress(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    monkeypatch.setenv("OMNIX_IMAGE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_IMAGE_URL", "http://127.0.0.1:5301")
    monkeypatch.setattr(Path, "is_file", lambda _path: True)
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    asset_store = MemoryAssetStore()
    job = job_store.create_job(
        CreateJobRequest(
            module="image-generation",
            type="image.generate",
            resource_class=ResourceClass.GPU_IMAGE,
            stages=[
                JobStage(id="generate-image", label="Generate image", resource_class=ResourceClass.GPU_IMAGE),
                JobStage(id="store-asset", label="Store image asset", resource_class=ResourceClass.CPU),
            ],
            input_payload={
                "prompt": "A progressive mountain lake",
                "provider_id": "image:mock",
                "width": 768,
                "height": 768,
            },
        )
    )
    progress_rows = [
        {"ok": True, "current": 4, "total": 32, "message": "Generating image"},
        {"ok": True, "current": 16, "total": 32, "message": "Generating image"},
        {"ok": True, "current": 32, "total": 32, "message": "Generating image"},
    ]
    progress_calls = []

    def fake_progress(_request_id):
        progress_calls.append(_request_id)
        return progress_rows.pop(0) if progress_rows else {"ok": True, "current": 32, "total": 32, "message": "Generating image"}

    monkeypatch.setattr("app.image_http_client.get_image_generation_progress", fake_progress)

    def generate(payload):
        assert payload["request_id"] == job.id
        time.sleep(1.25)
        return ImageGenerationResponse(
            ok=True,
            provider=payload["provider"],
            status="completed",
            local_path="result.png",
            width=payload["width"],
            height=payload["height"],
        )

    completed = execute_image_job(job_store, job, asset_store=asset_store, generate_fn=generate)

    assert completed.status.value == "completed"
    assert progress_calls


def test_invalid_image_job_fails_without_generation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    job = store.create_job(
        CreateJobRequest(
            module="image-generation",
            type="image.generate",
            resource_class=ResourceClass.GPU_IMAGE,
            input_payload={"prompt": "", "width": 768, "height": 768},
        )
    )

    failed = execute_image_job(store, job, generate_fn=lambda _payload: None)

    assert failed.status.value == "failed"
    assert failed.error is not None
    assert failed.error.code == "image_invalid_request"


def test_image_generation_failure_preserves_progress_and_marks_stage_failed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    job = store.create_job(
        CreateJobRequest(
            module="image-generation",
            type="image.generate",
            resource_class=ResourceClass.GPU_IMAGE,
            stages=[
                JobStage(id="generate-image", label="Generate image", resource_class=ResourceClass.GPU_IMAGE),
                JobStage(id="store-asset", label="Store image asset", resource_class=ResourceClass.CPU),
            ],
            input_payload={
                "prompt": "A failed mountain lake",
                "provider_id": "image:mock",
                "width": 768,
                "height": 768,
            },
        )
    )

    failed = execute_image_job(
        store,
        job,
        generate_fn=lambda _payload: ImageGenerationResponse(
            ok=False,
            provider="mock",
            status="failed",
            error="provider reset connection",
        ),
    )

    assert failed.status.value == "failed"
    assert failed.progress.message == "Generating image - 0%"
    assert failed.stages[0].status.value == "failed"
    assert failed.stages[0].error is not None
    assert failed.stages[0].error.message == "provider reset connection"
    assert failed.stages[1].status.value == "queued"
