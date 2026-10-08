from __future__ import annotations

from app.jobs.handlers import JobHandlerRegistry, registry_from_features
from app.jobs.models import JobRecord, JobStatus, ResourceClass
from app.persistence import job_store
from app.persistence.job_store import PostgresJobStoreAdapter
from app.runtime.feature_catalog import load_feature
from app.composition.runtime_composition import production_job_store
from app.runtime.tenant_context import local_tenant_context


def _job(*, job_type: str = "rpg.turn") -> JobRecord:
    return JobRecord(
        id="job:rpg:test",
        module="rpg",
        type=job_type,
        status=JobStatus.QUEUED,
        resource_class=ResourceClass.GPU_LLM,
        input_payload={
            "session_id": "session:test",
            "submission_id": "turn:test",
            "token": "must-not-be-logged",
        },
        created_at="2026-09-30T00:00:00+00:00",
        updated_at="2026-09-30T00:00:00+00:00",
    )


def test_job_handler_registry_notifies_each_lifecycle_method() -> None:
    observed: list[tuple[str, str]] = []

    class Observer:
        def on_created(self, job):
            observed.append(("created", job.id))

        def on_started(self, job):
            observed.append(("started", job.id))

        def on_completed(self, job):
            observed.append(("completed", job.id))

        def on_failed(self, job):
            observed.append(("failed", job.id))

    registry = JobHandlerRegistry()
    registry.register_observer(Observer())

    for event in ("created", "started", "completed", "failed"):
        registry.notify_observers(event, _job())

    assert observed == [
        ("created", "job:rpg:test"),
        ("started", "job:rpg:test"),
        ("completed", "job:rpg:test"),
        ("failed", "job:rpg:test"),
    ]


def test_rpg_feature_registers_debug_observer_only_when_enabled(monkeypatch) -> None:
    feature = load_feature("rpg")
    monkeypatch.setenv("OMNIX_RPG_DEBUG_LOGS", "0")
    assert registry_from_features((feature,)).observers == ()

    monkeypatch.setenv("OMNIX_RPG_DEBUG_LOGS", "1")
    observers = registry_from_features((feature,)).observers
    assert len(observers) == 1
    assert type(observers[0]).__name__ == "RpgJobDebugObserver"


def test_rpg_debug_observer_logs_safe_lifecycle_identity(monkeypatch) -> None:
    from app.apps.rpg.session.jobs.debug_observer import RpgJobDebugObserver

    records: list[dict] = []
    monkeypatch.setattr(
        "app.apps.rpg.foundation.debug_logging.log_rpg_event",
        lambda event, **kwargs: records.append({"event": event, **kwargs}),
    )

    RpgJobDebugObserver().on_failed(_job())

    assert records[0]["event"] == "job.failed"
    assert records[0]["session_id"] == "session:test"
    assert records[0]["turn_id"] == "turn:test"
    assert records[0]["fields"] == {
        "job_id": "job:rpg:test",
        "job_type": "rpg.turn",
        "status": "queued",
    }
    assert "must-not-be-logged" not in str(records)


def test_job_store_constructor_owns_chat_dependencies() -> None:
    database = object()
    context = local_tenant_context()
    owner = object()
    dispatcher = object()

    store = PostgresJobStoreAdapter(
        database=database,
        context=context,
        chat_execution_owner=owner,
        chat_dispatcher=dispatcher,
    )

    assert store.database is database
    assert store.context is context
    assert store.chat_execution_owner is owner
    assert store.chat_dispatcher is dispatcher


def test_production_job_factory_forwards_constructor_dependencies(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Adapter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "app.platform.chat.persistence.job_store.PostgresJobStoreAdapter",
        Adapter,
    )
    database = object()
    context = local_tenant_context()
    owner = object()
    dispatcher = object()

    production_job_store(
        database=database,
        context=context,
        chat_execution_owner=owner,
        chat_dispatcher=dispatcher,
    )

    assert captured == {
        "database": database,
        "context": context,
        "chat_execution_owner": owner,
        "chat_dispatcher": dispatcher,
    }


def test_created_observer_runs_after_durable_commit(monkeypatch) -> None:
    committed = False

    class JobRepository:
        def create_job(self, context, payload):
            return {"id": payload["id"]}

        def list_job_logs(self, context, *, job_id):
            return []

    class Work:
        jobs = JobRepository()
        connection = object()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            nonlocal committed
            committed = True

    class Observer:
        def __init__(self):
            self.created: list[str] = []

        def on_created(self, job):
            assert committed
            self.created.append(job.id)

        def on_started(self, job):
            pass

        def on_completed(self, job):
            pass

        def on_failed(self, job):
            pass

    store = PostgresJobStoreAdapter(
        database=object(),
        context=local_tenant_context(),
    )
    store._record = lambda _record: _job()
    store._new_job_id = lambda: "job:rpg:test"
    observer = Observer()
    registry = JobHandlerRegistry()
    registry.register_observer(observer)
    store.configure_handler_registry(registry)
    work = Work()
    monkeypatch.setattr(job_store, "unit_of_work", lambda _database: work)

    created = store.create_job(
        job_store.CreateJobRequest(
            module="rpg",
            type="rpg.turn",
            resource_class=ResourceClass.GPU_LLM,
            input_payload={"session_id": "session:test"},
        )
    )

    assert committed
    assert created.id == "job:rpg:test"
    assert observer.created == ["job:rpg:test"]
