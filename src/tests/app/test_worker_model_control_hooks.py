from __future__ import annotations

import pytest

from app.jobs import (
    GpuResidencyRequest,
    LocalJobExecutor,
    ResourceClass,
    SQLiteJobStore,
    SQLiteModelResidencyStore,
    create_model_evict_job_request,
    create_model_load_job_request,
    create_model_residency_handlers,
    create_worker_model_control_hooks,
    load_worker_model,
)
from app.jobs.models import JobStatus
from app.jobs.residency import ModelResidencyRecord, ModelResidencyStatus


def _request() -> GpuResidencyRequest:
    return GpuResidencyRequest(
        job_id="job:source",
        model_id="image:flux_klein",
        model_name="FLUX Klein",
        provider_id="image:flux_klein",
        module="image",
        resource_class=ResourceClass.GPU_IMAGE,
        worker_id="worker:image",
        worker_endpoint="http://127.0.0.1:5301",
        estimated_vram_mb=12000,
        compatibility_group="flux",
    )


def _record(worker_endpoint: str = "http://127.0.0.1:5301") -> ModelResidencyRecord:
    return ModelResidencyRecord(
        model_id="image:flux_klein",
        model_name="FLUX Klein",
        provider_id="image:flux_klein",
        module="image",
        resource_class=ResourceClass.GPU_IMAGE,
        status=ModelResidencyStatus.LOADING,
        worker_id="worker:image",
        worker_endpoint=worker_endpoint,
    )


@pytest.mark.asyncio
async def test_worker_model_control_hooks_complete_load_and_evict_through_executor(tmp_path) -> None:
    calls: list[tuple[str, dict, float]] = []

    def post_json(url: str, payload: dict, timeout: float) -> dict:
        calls.append((url, payload, timeout))
        return {"ok": True, "provider": payload["provider"], "url": url}

    load_hook, evict_hook = create_worker_model_control_hooks(post_json=post_json, timeout_seconds=12.0)
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    residency_store = SQLiteModelResidencyStore(tmp_path / "residency.sqlite")
    load_job = job_store.create_job(create_model_load_job_request(_request()))
    executor = LocalJobExecutor(
        job_store,
        create_model_residency_handlers(
            residency_store,
            load_model=load_hook,
            evict_model=evict_hook,
        ),
        worker_id="worker:image",
    )

    loaded = await executor.run_once([ResourceClass.GPU_IMAGE])

    assert loaded is not None
    assert loaded.id == load_job.id
    assert loaded.status == JobStatus.COMPLETED
    assert calls[0] == (
        "http://127.0.0.1:5301/provider/load",
        {
            "provider": "flux_klein",
            "provider_id": "image:flux_klein",
            "model_id": "image:flux_klein",
            "model_name": "FLUX Klein",
            "job_id": load_job.id,
            "resource_class": "gpu:image",
        },
        12.0,
    )
    assert loaded.output_refs[-1]["kind"] == "worker_model_control"
    assert loaded.output_refs[-1]["action"] == "loaded"

    loaded_record = residency_store.list_records()[0]
    evict_job = job_store.create_job(create_model_evict_job_request(loaded_record))
    evicted = await executor.run_once([ResourceClass.GPU_IMAGE])

    assert evicted is not None
    assert evicted.id == evict_job.id
    assert evicted.status == JobStatus.COMPLETED
    assert calls[1][0] == "http://127.0.0.1:5301/provider/unload"
    assert calls[1][1]["provider"] == "flux_klein"
    assert evicted.output_refs[-1]["kind"] == "worker_model_control"
    assert evicted.output_refs[-1]["action"] == "evicted"
    assert residency_store.list_records() == []


def test_worker_model_control_hook_rejects_missing_endpoint(tmp_path) -> None:
    request = _request().model_copy(update={"worker_endpoint": None})
    job = SQLiteJobStore(tmp_path / "jobs.sqlite").create_job(create_model_load_job_request(request))

    with pytest.raises(RuntimeError, match="worker_model_control_endpoint_missing"):
        load_worker_model(_record(worker_endpoint=""), job, post_json=lambda *_args: {"ok": True})


def test_worker_model_control_hook_raises_on_worker_error(tmp_path) -> None:
    job = SQLiteJobStore(tmp_path / "jobs.sqlite").create_job(create_model_load_job_request(_request()))

    with pytest.raises(RuntimeError, match="worker_model_control_loaded_failed:image_generation_disabled"):
        load_worker_model(
            _record(),
            job,
            post_json=lambda *_args: {"ok": False, "error": "image_generation_disabled"},
        )
