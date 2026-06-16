from __future__ import annotations

import pytest

from app.jobs.models import ResourceClass
from app.jobs.residency import (
    GpuResidencyPolicy,
    GpuResidencyRequest,
    ModelResidencyRecord,
    ModelResidencyStatus,
    ResidencyDecisionAction,
    SQLiteModelResidencyStore,
    create_model_evict_job_request,
    create_model_load_job_request,
    create_model_residency_handlers,
    get_model_residency_diagnostics,
    plan_model_residency,
)


def _request(
    model_id: str = "llm:local-chat",
    *,
    resource_class: ResourceClass = ResourceClass.GPU_LLM,
    estimated_vram_mb: int | None = 8000,
    compatibility_group: str | None = None,
) -> GpuResidencyRequest:
    return GpuResidencyRequest(
        job_id="job-1",
        model_id=model_id,
        model_name=model_id,
        provider_id="lmstudio",
        module="chatbot",
        resource_class=resource_class,
        estimated_vram_mb=estimated_vram_mb,
        compatibility_group=compatibility_group,
    )


def _loaded(
    model_id: str,
    *,
    resource_class: ResourceClass = ResourceClass.GPU_LLM,
    estimated_vram_mb: int | None = 8000,
    compatibility_group: str | None = None,
    status: ModelResidencyStatus = ModelResidencyStatus.LOADED,
) -> ModelResidencyRecord:
    return ModelResidencyRecord(
        model_id=model_id,
        model_name=model_id,
        provider_id="local",
        module="chatbot",
        resource_class=resource_class,
        status=status,
        worker_id="worker:gpu",
        worker_endpoint="http://127.0.0.1:9001",
        estimated_vram_mb=estimated_vram_mb,
        compatibility_group=compatibility_group,
    )


def test_cpu_and_network_jobs_do_not_block_on_loaded_gpu_model() -> None:
    loaded = [_loaded("image:flux", resource_class=ResourceClass.GPU_IMAGE)]

    cpu_decision = plan_model_residency(_request(resource_class=ResourceClass.CPU), loaded)
    network_decision = plan_model_residency(_request(resource_class=ResourceClass.NETWORK), loaded)

    assert cpu_decision.action == ResidencyDecisionAction.CAN_RUN
    assert cpu_decision.reason == "non_gpu_job"
    assert network_decision.action == ResidencyDecisionAction.CAN_RUN
    assert network_decision.reason == "non_gpu_job"


def test_conservative_policy_evicts_incompatible_loaded_gpu_model() -> None:
    decision = plan_model_residency(
        _request("tts:qwen", resource_class=ResourceClass.GPU_TTS),
        [_loaded("image:flux", resource_class=ResourceClass.GPU_IMAGE)],
    )

    assert decision.action == ResidencyDecisionAction.EVICT_FIRST
    assert decision.reason == "conservative_single_gpu_policy"
    assert decision.eviction_model_ids == ["image:flux"]


def test_loaded_requested_model_can_run_without_evicting_itself() -> None:
    decision = plan_model_residency(_request("llm:local-chat"), [_loaded("llm:local-chat")])

    assert decision.action == ResidencyDecisionAction.CAN_RUN
    assert decision.reason == "requested_model_already_loaded"
    assert decision.eviction_model_ids == []


def test_compatible_models_may_share_when_policy_allows_and_vram_fits() -> None:
    decision = plan_model_residency(
        _request("llm:small-b", estimated_vram_mb=6000, compatibility_group="small-local"),
        [_loaded("llm:small-a", estimated_vram_mb=6000, compatibility_group="small-local")],
        GpuResidencyPolicy(
            total_vram_mb=16000,
            allow_co_residency=True,
            allow_matching_compatibility_group=True,
        ),
    )

    assert decision.action == ResidencyDecisionAction.CAN_RUN
    assert decision.reason == "compatible_vram_available"


def test_unknown_vram_never_overcommits_even_for_compatible_models() -> None:
    decision = plan_model_residency(
        _request("llm:small-b", estimated_vram_mb=None, compatibility_group="small-local"),
        [_loaded("llm:small-a", estimated_vram_mb=6000, compatibility_group="small-local")],
        GpuResidencyPolicy(
            total_vram_mb=16000,
            allow_co_residency=True,
            allow_matching_compatibility_group=True,
        ),
    )

    assert decision.action == ResidencyDecisionAction.EVICT_FIRST
    assert decision.reason == "unknown_vram_requires_exclusive_gpu"
    assert decision.eviction_model_ids == ["llm:small-a"]


def test_loading_or_unloading_model_queues_new_gpu_work() -> None:
    decision = plan_model_residency(
        _request("image:flux-b", resource_class=ResourceClass.GPU_IMAGE),
        [_loaded("image:flux-a", resource_class=ResourceClass.GPU_IMAGE, status=ModelResidencyStatus.LOADING)],
        GpuResidencyPolicy(allow_co_residency=True),
    )

    assert decision.action == ResidencyDecisionAction.QUEUE
    assert decision.reason == "model_transition_in_progress"
    assert decision.blocking_model_ids == ["image:flux-a"]


def test_requested_model_error_blocks_with_diagnostics() -> None:
    errored = _loaded("llm:broken", status=ModelResidencyStatus.ERROR)
    errored.error = "load_failed"

    decision = plan_model_residency(_request("llm:broken"), [errored])

    assert decision.action == ResidencyDecisionAction.BLOCKED
    assert decision.reason == "requested_model_in_error"
    assert decision.diagnostics == [
        {"kind": "model_residency_error", "model_id": "llm:broken", "message": "load_failed"}
    ]


def test_model_load_and_evict_transitions_are_job_requests() -> None:
    load_request = create_model_load_job_request(
        _request(
            "image:flux",
            resource_class=ResourceClass.GPU_IMAGE,
            estimated_vram_mb=12000,
            compatibility_group="flux",
        ),
        priority=5,
    )
    evict_request = create_model_evict_job_request(
        _loaded("image:flux", resource_class=ResourceClass.GPU_IMAGE, estimated_vram_mb=12000),
        priority=6,
    )

    assert load_request.module == "models"
    assert load_request.type == "model.load"
    assert load_request.resource_class == ResourceClass.GPU_IMAGE
    assert load_request.priority == 5
    assert load_request.stages[0].id == "load-model"
    assert load_request.input_payload["model_id"] == "image:flux"
    assert load_request.compat == {"residency_transition": "load"}

    assert evict_request.module == "models"
    assert evict_request.type == "model.evict"
    assert evict_request.resource_class == ResourceClass.GPU_IMAGE
    assert evict_request.priority == 6
    assert evict_request.stages[0].id == "evict-model"
    assert evict_request.input_payload["model_id"] == "image:flux"
    assert evict_request.compat == {"residency_transition": "evict"}


def test_model_residency_diagnostics_reports_policy_and_error_warnings() -> None:
    errored = _loaded("llm:broken", status=ModelResidencyStatus.ERROR)
    errored.error = "load_failed"

    diagnostics = get_model_residency_diagnostics(
        [
            _loaded("llm:small", estimated_vram_mb=None),
            errored,
        ],
        GpuResidencyPolicy(total_vram_mb=16000, allow_co_residency=True),
    )

    assert diagnostics.status == "degraded"
    assert diagnostics.policy.total_vram_mb == 16000
    assert diagnostics.policy.allow_co_residency is True
    assert diagnostics.warnings == [
        "unknown_vram_records_require_exclusive_gpu",
        "model_residency_errors_present",
    ]


def test_sqlite_model_residency_store_persists_worker_reports(tmp_path) -> None:
    db_path = tmp_path / "residency.sqlite"
    store = SQLiteModelResidencyStore(db_path)
    loaded = _loaded("llm:local-chat", estimated_vram_mb=9000)

    store.upsert_record(loaded)

    next_store = SQLiteModelResidencyStore(db_path)
    records = next_store.list_records()
    diagnostics = next_store.diagnostics()

    assert len(records) == 1
    assert records[0].model_id == "llm:local-chat"
    assert records[0].worker_id == "worker:gpu"
    assert records[0].status == ModelResidencyStatus.LOADED
    assert diagnostics.status == "active"

    assert next_store.delete_record("llm:local-chat") is True
    assert next_store.list_records() == []
    assert next_store.diagnostics().status == "idle"


@pytest.mark.asyncio
async def test_model_residency_handlers_complete_load_and_evict_jobs(tmp_path) -> None:
    from app.jobs import LocalJobExecutor, SQLiteJobStore

    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    residency_store = SQLiteModelResidencyStore(tmp_path / "residency.sqlite")
    hook_calls: list[tuple[str, str, ModelResidencyStatus]] = []
    load_job = job_store.create_job(
        create_model_load_job_request(
            _request(
                "llm:small-a",
                estimated_vram_mb=6000,
                compatibility_group="small-local",
            )
        )
    )
    executor = LocalJobExecutor(
        job_store,
        create_model_residency_handlers(
            residency_store,
            load_model=lambda record, _job: {
                "logs": [{"level": "info", "message": "load hook ran"}],
                "output_refs": [{"kind": "provider_load", "model_id": record.model_id}],
            }
            if not hook_calls.append(("load", record.model_id, record.status))
            else {},
            evict_model=lambda record, _job: {
                "logs": [{"level": "info", "message": "evict hook ran"}],
                "output_refs": [{"kind": "provider_evict", "model_id": record.model_id}],
            }
            if not hook_calls.append(("evict", record.model_id, record.status))
            else {},
        ),
        worker_id="worker:gpu",
    )

    loaded = await executor.run_once([ResourceClass.GPU_LLM])

    records = residency_store.list_records()
    events_after_load = job_store.list_events(after_id=0)
    assert loaded is not None
    assert loaded.id == load_job.id
    assert loaded.status == "completed"
    assert records[0].model_id == "llm:small-a"
    assert records[0].status == ModelResidencyStatus.LOADED
    assert records[0].worker_id == "worker:gpu"
    assert ("load", "llm:small-a", ModelResidencyStatus.LOADING) in hook_calls
    assert {"kind": "provider_load", "model_id": "llm:small-a"} in loaded.output_refs
    assert events_after_load[-1].event_type == "job.completed"

    evict_job = job_store.create_job(create_model_evict_job_request(records[0]))
    evicted = await executor.run_once([ResourceClass.GPU_LLM])

    assert evicted is not None
    assert evicted.id == evict_job.id
    assert evicted.status == "completed"
    assert ("evict", "llm:small-a", ModelResidencyStatus.UNLOADING) in hook_calls
    assert {"kind": "provider_evict", "model_id": "llm:small-a"} in evicted.output_refs
    assert residency_store.list_records() == []
    assert job_store.list_events(after_id=events_after_load[-1].id)[-1].event_type == "job.completed"


@pytest.mark.asyncio
async def test_model_residency_load_hook_failure_records_error_and_fails_job(tmp_path) -> None:
    from app.jobs import LocalJobExecutor, SQLiteJobStore

    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    residency_store = SQLiteModelResidencyStore(tmp_path / "residency.sqlite")
    load_job = job_store.create_job(create_model_load_job_request(_request("llm:broken")))

    def fail_load(_record, _job):
        raise RuntimeError("provider load failed")

    executor = LocalJobExecutor(
        job_store,
        create_model_residency_handlers(residency_store, load_model=fail_load),
        worker_id="worker:gpu",
    )

    failed = await executor.run_once([ResourceClass.GPU_LLM])
    records = residency_store.list_records()
    events = job_store.list_events()

    assert failed is not None
    assert failed.id == load_job.id
    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.message == "provider load failed"
    assert records[0].model_id == "llm:broken"
    assert records[0].status == ModelResidencyStatus.ERROR
    assert records[0].error == "provider load failed"
    assert events[-1].event_type == "job.failed"
