from __future__ import annotations

from pathlib import Path

import pytest

from app.jobs.models import ResourceClass
from app.providers.cache_status import (
    ProviderModelCacheEntry,
    ProviderModelCachePayload,
    ProviderModelCacheStatusService,
    ProviderModelRefreshRequest,
    SQLiteProviderModelRefreshStore,
    create_provider_model_refresh_handlers,
    create_provider_model_refresh_job_request,
)
from app.providers.facade import (
    ModelSummary,
    ProviderCapability,
    ProviderFacadePayload,
    ProviderSummary,
)


def _provider_payload() -> ProviderFacadePayload:
    return ProviderFacadePayload(
        providers=[
            ProviderSummary(
                id="llm:test",
                label="Test LLM",
                family="llm",
                capabilities=[ProviderCapability.CHAT, ProviderCapability.DIAGNOSTICS],
                status="available",
                source="test",
            )
        ],
        models=[
            ModelSummary(
                id="llm:test:small",
                label="test: small",
                provider_id="llm:test",
                capabilities=[ProviderCapability.CHAT],
                location="local",
                metadata={"source": "test"},
            )
        ],
    )


def _cache_payload(status: str = "ready") -> ProviderModelCachePayload:
    return ProviderModelCachePayload(
        status=status,
        entries=[
            ProviderModelCacheEntry(
                id="llm:test:small",
                provider_id="llm:test",
                model_id="small",
                status="available",
                source="test",
            )
        ],
        diagnostics=[] if status == "ready" else [{"kind": "cache_degraded", "id": "llm:test"}],
    )


class _FakeProviderFacade:
    def payload(self) -> ProviderFacadePayload:
        return _provider_payload()


def test_provider_model_cache_status_reports_missing_local_paths_without_provider_imports(tmp_path: Path) -> None:
    existing = tmp_path / "models" / "image"
    existing.mkdir(parents=True)

    service = ProviderModelCacheStatusService(
        settings_loader=lambda: {
            "openrouter": {"model": "openai/gpt-4o-mini"},
            "cerebras": {},
            "llamacpp": {"model": "local.gguf", "download_location": "llm"},
            "faster-qwen3-tts": {"model_name": "Qwen/Qwen3-TTS", "model_dir": str(tmp_path / "missing-tts")},
            "image": {"flux_klein": {"repo_id": "flux", "local_dir": str(existing)}},
            "rpg_visual": {"flux_klein": {"repo_id": "flux-rpg", "local_dir": str(tmp_path / "missing-rpg")}},
            "tts_worker_url": "http://127.0.0.1:9201",
            "stt_worker_url": "",
            "image_worker_url": "http://127.0.0.1:9203",
        },
        url_reachable=lambda url: url in {"http://127.0.0.1:9201", "http://127.0.0.1:9203"},
        models_root=tmp_path / "models",
    )

    payload = service.payload()
    entries = {entry.id: entry for entry in payload.entries}

    assert payload.status == "degraded"
    assert entries["llm:openrouter:model"].status == "configured"
    assert entries["llm:cerebras:model"].status == "not_configured"
    assert entries["llm:llamacpp"].status == "missing_path"
    assert entries["tts:faster-qwen3-tts"].status == "missing_path"
    assert entries["image:flux_klein"].status == "available"
    assert entries["rpg_visual:flux_klein"].status == "missing_path"
    assert entries["worker:tts"].status == "configured"
    assert entries["worker:stt"].status == "not_configured"
    assert entries["worker:image"].status == "configured"
    assert {item["id"] for item in payload.diagnostics} == {
        "llm:llamacpp",
        "tts:faster-qwen3-tts",
        "rpg_visual:flux_klein",
    }


def test_provider_model_cache_status_is_ready_when_no_missing_paths(tmp_path: Path) -> None:
    local_model = tmp_path / "models" / "llm" / "local.gguf"
    tts_model = tmp_path / "tts"
    local_model.parent.mkdir(parents=True)
    local_model.write_bytes(b"model")
    tts_model.mkdir()

    service = ProviderModelCacheStatusService(
        settings_loader=lambda: {
            "llamacpp": {"model": "local.gguf", "download_location": "llm"},
            "faster-qwen3-tts": {"model_name": "Qwen/Qwen3-TTS", "model_dir": str(tts_model)},
            "image": {"flux_klein": {"repo_id": "flux"}},
            "rpg_visual": {"flux_klein": {"repo_id": "flux-rpg"}},
        },
        models_root=tmp_path / "models",
    )

    payload = service.payload()

    assert payload.status == "ready"
    assert payload.diagnostics == []


def test_provider_model_cache_status_reports_unreachable_configured_local_servers(tmp_path: Path) -> None:
    service = ProviderModelCacheStatusService(
        settings_loader=lambda: {
            "lmstudio": {"base_url": "http://127.0.0.1:1234"},
            "llamacpp": {"base_url": "http://127.0.0.1:8080"},
            "tts_worker_url": "http://127.0.0.1:9201",
        },
        url_reachable=lambda url: url == "http://127.0.0.1:8080",
        models_root=tmp_path / "models",
    )

    payload = service.payload()
    entries = {entry.id: entry for entry in payload.entries}

    assert payload.status == "degraded"
    assert entries["server:lmstudio"].status == "unreachable"
    assert entries["server:llamacpp"].status == "configured"
    assert entries["worker:tts"].status == "unreachable"
    assert {item["id"] for item in payload.diagnostics} == {"server:lmstudio", "worker:tts"}


def test_provider_model_refresh_job_request_is_cpu_bound_and_event_visible() -> None:
    request = ProviderModelRefreshRequest(scope="models", reason="test-refresh", priority=7)

    job_request = create_provider_model_refresh_job_request(request)

    assert job_request.module == "platform"
    assert job_request.type == "providers.models.refresh"
    assert job_request.resource_class == ResourceClass.CPU
    assert job_request.priority == 7
    assert job_request.input_payload == {"scope": "models", "reason": "test-refresh"}
    assert [stage.id for stage in job_request.stages] == [
        "discover-providers",
        "discover-local-models",
        "publish-cache-status",
    ]
    assert all(stage.resource_class == ResourceClass.CPU for stage in job_request.stages)
    assert job_request.compat["contract"] == "provider_model_refresh_v1"


def test_provider_model_refresh_store_persists_snapshots(tmp_path: Path) -> None:
    db_path = tmp_path / "provider-model-refresh.sqlite"
    store = SQLiteProviderModelRefreshStore(db_path)

    snapshot = store.record_snapshot(
        scope="all",
        reason="manual",
        provider_payload=_provider_payload(),
        cache_payload=_cache_payload("degraded"),
    )

    next_store = SQLiteProviderModelRefreshStore(db_path)
    history = next_store.history()
    latest = next_store.latest_snapshot()

    assert latest is not None
    assert latest.id == snapshot.id
    assert latest.scope == "all"
    assert latest.reason == "manual"
    assert latest.status == "degraded"
    assert latest.provider_count == 1
    assert latest.model_count == 1
    assert latest.cache_status == "degraded"
    assert latest.diagnostics == [{"kind": "cache_degraded", "id": "llm:test"}]
    assert history.snapshots[0].id == snapshot.id


@pytest.mark.asyncio
async def test_provider_model_refresh_handler_completes_job_and_records_snapshot(tmp_path: Path) -> None:
    from app.jobs import LocalJobExecutor, SQLiteJobStore

    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    refresh_store = SQLiteProviderModelRefreshStore(tmp_path / "refresh.sqlite")
    job = job_store.create_job(
        create_provider_model_refresh_job_request(
            ProviderModelRefreshRequest(scope="models", reason="button-click", priority=4)
        )
    )
    executor = LocalJobExecutor(
        job_store,
        create_provider_model_refresh_handlers(
            refresh_store,
            provider_facade_factory=_FakeProviderFacade,
            cache_status_factory=_cache_payload,
        ),
    )

    completed = await executor.run_once([ResourceClass.CPU])
    latest = refresh_store.latest_snapshot()
    events = job_store.list_events()

    assert completed is not None
    assert completed.id == job.id
    assert completed.status == "completed"
    assert latest is not None
    assert latest.scope == "models"
    assert latest.reason == "button-click"
    assert latest.provider_count == 1
    assert latest.model_count == 1
    assert completed.output_refs == [
        {
            "kind": "provider_model_refresh",
            "snapshot_id": latest.id,
            "scope": "models",
            "provider_count": 1,
            "model_count": 1,
            "cache_status": "ready",
            "status": "ready",
        }
    ]
    assert completed.logs[0]["snapshot_id"] == latest.id
    assert events[-1].event_type == "job.completed"


@pytest.mark.asyncio
async def test_provider_model_refresh_handler_failure_uses_shared_failed_event(tmp_path: Path) -> None:
    from app.jobs import LocalJobExecutor, SQLiteJobStore

    class BrokenFacade:
        def payload(self) -> ProviderFacadePayload:
            raise RuntimeError("discovery failed")

    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    refresh_store = SQLiteProviderModelRefreshStore(tmp_path / "refresh.sqlite")
    job = job_store.create_job(
        create_provider_model_refresh_job_request(ProviderModelRefreshRequest(scope="providers"))
    )
    executor = LocalJobExecutor(
        job_store,
        create_provider_model_refresh_handlers(refresh_store, provider_facade_factory=BrokenFacade),
    )

    failed = await executor.run_once([ResourceClass.CPU])
    events = job_store.list_events()

    assert failed is not None
    assert failed.id == job.id
    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.message == "discovery failed"
    assert refresh_store.list_snapshots() == []
    assert events[-1].event_type == "job.failed"
