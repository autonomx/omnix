"""Submission adapter for shared image jobs."""
from __future__ import annotations

from typing import Any

from .models import CreateJobRequest, JobRecord, JobStage, ResourceClass
from .store import InMemoryJobStore


def enqueue_image_job(
    store: InMemoryJobStore,
    *,
    payload: dict[str, Any],
    owner_id: str | None = None,
    priority: int = 0,
) -> JobRecord:
    """Submit image generation only through the durable shared job store."""
    return store.create_job(
        CreateJobRequest(
            owner_id=owner_id,
            module="image-generation",
            type="image.generate",
            resource_class=ResourceClass.GPU_IMAGE,
            priority=priority,
            stages=[
                JobStage(
                    id="generate-image",
                    label="Generate image",
                    resource_class=ResourceClass.GPU_IMAGE,
                ),
                JobStage(
                    id="store-asset",
                    label="Store image asset",
                    resource_class=ResourceClass.CPU,
                ),
            ],
            input_payload=payload,
            compat={
                "legacy_system": "src/app/image/job_queue.py",
                "legacy_queue_bypassed": True,
            },
        )
    )
