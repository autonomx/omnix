from app.jobs.inline_execution import mark_inline_execution
from app.jobs.models import CreateJobRequest, JobProgress, JobStatus, ResourceClass
from app.persistence.job_store import PostgresJobStoreAdapter
from app.platform.chat.persistence.job_store import PostgresJobStoreAdapter as RuntimePostgresJobStoreAdapter


def test_mark_inline_execution_preserves_existing_compatibility_flags() -> None:
    request = CreateJobRequest(
        module="voice",
        type="tts.multi_speaker_synthesize",
        resource_class=ResourceClass.CPU,
        compat={"client_contract": "voice_studio_v2"},
    )

    marked = mark_inline_execution(request)

    assert marked.compat == {
        "client_contract": "voice_studio_v2",
        "inline_execution": True,
    }
    assert request.compat == {"client_contract": "voice_studio_v2"}


def test_postgres_compat_logs_preserve_structured_entries() -> None:
    structured = {"level": "info", "message": "audio saved", "content": "path.wav"}

    assert PostgresJobStoreAdapter._compat_log(structured) == structured
    assert PostgresJobStoreAdapter._compat_log("legacy log") == {
        "level": "info",
        "message": "legacy log",
    }


def test_postgres_compat_lease_uses_persisted_start_as_claim_time() -> None:
    adapter = object.__new__(PostgresJobStoreAdapter)
    record = adapter._record(
        {
            "id": "job:leased",
            "owner_user_id": "user:local",
            "module": "rpg",
            "job_type": "rpg.turn",
            "status": "leased",
            "resource_class": "cpu",
            "priority": 0,
            "progress": {},
            "input_payload": {},
            "output_refs": [],
            "error": None,
            "lease_owner": "worker:rpg",
            "lease_token": "lease-token",
            "lease_expires_at": "2026-07-16T02:00:00+00:00",
            "started_at": "2026-07-16T01:00:00+00:00",
            "completed_at": None,
            "created_at": "2026-07-16T00:59:00+00:00",
            "updated_at": "2026-07-16T01:00:01+00:00",
            "metadata": {},
        }
    )

    assert record.lease is not None
    assert record.lease.claimed_at == "2026-07-16T01:00:00+00:00"
    assert record.lease.expires_at == "2026-07-16T02:00:00+00:00"


def test_postgres_compat_normalizes_legacy_code_only_error() -> None:
    adapter = object.__new__(PostgresJobStoreAdapter)
    record = adapter._record(
        {
            "id": "job:expired",
            "owner_user_id": "user:local",
            "module": "rpg",
            "job_type": "rpg.campaign_genesis.generate",
            "status": "failed",
            "resource_class": "rpg_campaign_genesis",
            "priority": 0,
            "progress": {},
            "input_payload": {},
            "output_refs": [],
            "error": {"code": "lease_expired"},
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "created_at": "2026-07-16T00:00:00Z",
            "updated_at": "2026-07-16T00:01:00Z",
            "started_at": "2026-07-16T00:00:10Z",
            "completed_at": "2026-07-16T00:01:00Z",
            "metadata": {},
        }
    )

    assert record.error is not None
    assert record.error.code == "lease_expired"
    assert record.error.message == "lease_expired"


def test_postgres_compat_reads_fractional_render_progress() -> None:
    adapter = object.__new__(PostgresJobStoreAdapter)
    record = adapter._record(
        {
            "id": "job:render-progress",
            "owner_user_id": "user:local",
            "module": "audiobook",
            "job_type": "audiobook.render",
            "status": "running",
            "resource_class": "gpu:tts",
            "priority": 0,
            "progress": {"current": 32.009765625, "total": 50, "message": "rendering"},
            "input_payload": {},
            "output_refs": [],
            "error": None,
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "created_at": "2026-07-16T00:00:00Z",
            "updated_at": "2026-07-16T00:01:00Z",
            "started_at": "2026-07-16T00:00:10Z",
            "completed_at": None,
            "metadata": {},
        }
    )

    assert record.progress.current == 32.009765625
    assert record.progress.total == 50
    assert JobProgress(current=1, total=2).model_dump()["current"] == 1


def test_postgres_compat_rechecks_inline_owner_on_idempotent_mark_running(monkeypatch) -> None:
    adapter = object.__new__(PostgresJobStoreAdapter)
    running = adapter._record(
        {
            "id": "job:inline-running",
            "owner_user_id": "user:local",
            "module": "chat",
            "job_type": "chat.generate",
            "status": "running",
            "resource_class": "network",
            "priority": 0,
            "progress": {},
            "input_payload": {},
            "output_refs": [],
            "error": None,
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "created_at": "2026-07-16T00:00:00Z",
            "updated_at": "2026-07-16T00:01:00Z",
            "started_at": "2026-07-16T00:00:10Z",
            "completed_at": None,
            "metadata": {"compat_contract": {"compat": {"inline_execution": True}}},
        }
    )
    adapter.get_job = lambda job_id: running  # type: ignore[method-assign]
    adapter._record = lambda record: running  # type: ignore[method-assign]
    adapter.database = object()
    adapter.context = type("Context", (), {"workspace_id": "workspace:test"})()
    adapter.chat_execution_owner = type("Owner", (), {"node_id": "gateway:test"})()
    adapter.handler_registry = None
    calls = []

    class Jobs:
        def mark_record_only_running(self, context, **kwargs):
            calls.append((context.workspace_id, kwargs))
            return {"id": running.id}

        def list_job_logs(self, context, *, job_id):
            return []

    class Work:
        jobs = Jobs()

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def commit(self):
            pass

    monkeypatch.setattr(
        "app.persistence.job_store.unit_of_work", lambda _database: Work()
    )

    assert running.status == JobStatus.RUNNING
    assert adapter.mark_running(running.id) is running
    assert calls == [(
        "workspace:test",
        {"job_id": running.id, "execution_owner": "gateway:test", "submission_claim_token": None},
    )]


def test_postgres_runtime_progress_preserves_the_active_stage(monkeypatch) -> None:
    adapter = object.__new__(RuntimePostgresJobStoreAdapter)
    running = adapter._record(
        {
            "id": "job:research-progress",
            "owner_user_id": "user:local",
            "module": "assistant",
            "job_type": "assistant.deep_research",
            "status": "running",
            "resource_class": "network",
            "priority": 0,
            "progress": {},
            "input_payload": {},
            "output_refs": [],
            "error": None,
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "created_at": "2026-07-16T00:00:00Z",
            "updated_at": "2026-07-16T00:01:00Z",
            "started_at": "2026-07-16T00:00:10Z",
            "completed_at": None,
            "metadata": {
                "compat_contract": {
                    "compat": {"inline_execution": True},
                    "stages": [
                        {
                            "id": "planning",
                            "label": "Planning research",
                            "status": "queued",
                            "resource_class": "cpu",
                        },
                        {
                            "id": "searching",
                            "label": "Searching the web",
                            "status": "queued",
                            "resource_class": "network",
                        },
                    ],
                }
            },
        }
    )
    persisted: dict[str, object] = {}
    monkeypatch.setattr(
        PostgresJobStoreAdapter,
        "update_progress",
        lambda self, job_id, progress, **kwargs: running,
    )
    monkeypatch.setattr(
        adapter,
        "update_job_stages",
        lambda job_id, stages, **kwargs: persisted.update(stages=stages) or running,
    )

    updated = adapter.update_progress(
        running.id,
        JobProgress(current=1, total=6, message="Searching current sources"),
        stage_id="searching",
        stage_status=JobStatus.RUNNING,
        worker_id="worker:test",
        lease_token="lease:test",
    )

    assert updated is running
    stages = persisted["stages"]
    assert isinstance(stages, list)
    assert stages[1].status == JobStatus.RUNNING
    assert stages[1].progress.message == "Searching current sources"
