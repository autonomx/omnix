from __future__ import annotations

import threading
from pathlib import Path

from app.platform.image.models import ImageGenerationResponse
from app.jobs import CreateJobRequest, ResourceClass
from app.jobs.models import JobStage
from app.platform.image.jobs import execute_image_job
from tests.support.in_memory_jobs import InMemoryJobStore


class MemoryAssetStore:
    def __init__(self) -> None:
        self.assets = []

    def upsert_asset(self, asset):
        self.assets.append(asset)
        return asset


def test_image_job_executes_and_persists_shared_asset(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(Path, "is_file", lambda _path: True)
    job_store = InMemoryJobStore(tmp_path / "jobs")
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
    monkeypatch.setattr(Path, "is_file", lambda _path: True)
    job_store = InMemoryJobStore(tmp_path / "jobs")
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
    monkeypatch.setattr(Path, "is_file", lambda _path: True)
    job_store = InMemoryJobStore(tmp_path / "jobs")
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


def test_image_job_reports_provider_steps_without_a_poller_thread(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(Path, "is_file", lambda _path: True)
    job_store = InMemoryJobStore(tmp_path / "jobs")
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
    reported = []
    record = job_store.update_progress

    def update_progress(job_id, **progress):
        reported.append((progress["current"], progress["message"]))
        return record(job_id, **progress)

    monkeypatch.setattr(job_store, "update_progress", update_progress)
    threads_before = {thread.name for thread in threading.enumerate()}

    def generate(payload):
        assert payload["request_id"] == job.id
        for step in (4, 16, 16, 32):
            payload["_progress_callback"](step, 32, "Generating image")
        assert {thread.name for thread in threading.enumerate()} <= threads_before
        return ImageGenerationResponse(
            ok=True,
            provider=payload["provider"],
            status="completed",
            local_path="result.png",
            width=payload["width"],
            height=payload["height"],
        )

    completed = execute_image_job(job_store, job, asset_store=MemoryAssetStore(), generate_fn=generate)

    assert completed.status.value == "completed"
    steps = [entry for entry in reported if entry[1].startswith(("Generating image -", "Finalizing"))]
    assert steps == [(0, "Generating image - 0%"), (11, "Generating image - 11%"), (48, "Generating image - 48%"), (95, "Finalizing image...")]


def test_invalid_image_job_fails_without_generation(monkeypatch, tmp_path) -> None:
    store = InMemoryJobStore(tmp_path / "jobs")
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
    store = InMemoryJobStore(tmp_path / "jobs")
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
