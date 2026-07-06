from __future__ import annotations

from app.image.models import ImageGenerationResponse
from app.jobs import CreateJobRequest, ResourceClass, SQLiteJobStore
from app.jobs.image_inline import execute_image_job


def test_image_job_executes_and_completes(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    job = store.create_job(
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
        store,
        job,
        generate_fn=lambda payload: ImageGenerationResponse(
            ok=True,
            provider=payload["provider"],
            status="completed",
            local_path=str(tmp_path / "result.png"),
            width=payload["width"],
            height=payload["height"],
        ),
    )

    assert completed.status.value == "completed"
    assert completed.output_refs[0]["provider"] == "mock"
    assert completed.output_refs[0]["title"] == "A luminous mountain lake"


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
