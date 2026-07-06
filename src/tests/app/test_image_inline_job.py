from __future__ import annotations

from pathlib import Path

from app.image.models import ImageGenerationResponse
from app.jobs import CreateJobRequest, ResourceClass, SQLiteJobStore
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
