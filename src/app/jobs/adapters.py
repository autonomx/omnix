"""Compatibility submission adapters for legacy feature queues."""
from __future__ import annotations

from typing import Any, Protocol

from .models import CreateJobRequest, JobRecord, JobStage, ResourceClass
from .store import SQLiteJobStore


class LegacyTTSQueue(Protocol):
    def enqueue(
        self,
        text: str,
        speaker: str | None = None,
        voice_id: str | None = None,
        chunk_index: int = -1,
        **kwargs: Any,
    ) -> str:
        ...


def enqueue_tts_job(
    store: SQLiteJobStore,
    legacy_queue: LegacyTTSQueue,
    *,
    text: str,
    speaker: str | None = None,
    voice_id: str | None = None,
    chunk_index: int = -1,
    owner_id: str | None = None,
    priority: int = 0,
    **kwargs: Any,
) -> JobRecord:
    """Submit TTS through the shared job store while preserving legacy execution."""
    legacy_job_id = legacy_queue.enqueue(
        text,
        speaker=speaker,
        voice_id=voice_id,
        chunk_index=chunk_index,
        **kwargs,
    )
    stage_id = "chunk:0000" if chunk_index < 0 else f"chunk:{chunk_index:04d}"
    return store.create_job(
        CreateJobRequest(
            owner_id=owner_id,
            module="voice",
            type="tts.synthesize",
            resource_class=ResourceClass.GPU_TTS,
            priority=priority,
            stages=[
                JobStage(
                    id=stage_id,
                    label="Synthesize speech",
                    resource_class=ResourceClass.GPU_TTS,
                ),
                JobStage(
                    id="reassemble",
                    label="Reassemble audio",
                    resource_class=ResourceClass.CPU,
                ),
            ],
            input_payload={
                "text": text,
                "speaker": speaker,
                "voice_id": voice_id,
                "chunk_index": chunk_index,
                "options": kwargs,
            },
            compat={
                "legacy_system": "src/app/job_queue.py",
                "legacy_job_id": legacy_job_id,
            },
        )
    )


def enqueue_image_job(
    store: SQLiteJobStore,
    *,
    payload: dict[str, Any],
    owner_id: str | None = None,
    priority: int = 0,
) -> JobRecord:
    """Submit image generation through shared jobs and the legacy image queue."""
    from app.image.job_queue import enqueue_image_job as enqueue_legacy_image_job

    legacy_job = enqueue_legacy_image_job(payload)
    return store.create_job(
        CreateJobRequest(
            owner_id=owner_id,
            module="image",
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
                "legacy_job_id": legacy_job.get("job_id"),
                "legacy_status": legacy_job.get("status"),
            },
        )
    )
