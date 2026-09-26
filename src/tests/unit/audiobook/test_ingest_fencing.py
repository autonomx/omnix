from contextlib import contextmanager
from types import SimpleNamespace

from app.audiobook.repository import PostgresAudiobookRepository
from app.audiobook.worker import run_ingest_once
from app.persistence.tenant import local_tenant_context


class Connection:
    def __init__(self, current, latest=None):
        self.current = current
        self.latest = latest

    def execute(self, sql, params):
        self.sql = sql
        return self

    def fetchone(self):
        if "FROM omnix_assets" in self.sql:
            return ("source-key", "checksum")
        if "FROM omnix_jobs" in self.sql:
            return (self.latest,) if self.latest else None
        return self.current


def test_only_latest_requested_ingest_can_publish():
    context = local_tenant_context()
    repository = PostgresAudiobookRepository(Connection(("new-job",)))
    assert not repository.is_current_ingest(context, project_id="book", job_id="old-job")
    assert repository.is_current_ingest(context, project_id="book", job_id="new-job")
    assert "FOR UPDATE" in repository.connection.sql
    assert not PostgresAudiobookRepository(Connection(None)).is_current_ingest(
        context, project_id="deleted-book", job_id="new-job",
    )


def test_legacy_ingest_without_pointer_uses_latest_durable_request():
    repository = PostgresAudiobookRepository(Connection((None,), latest="new-job"))
    context = local_tenant_context()
    assert not repository.is_current_ingest(context, project_id="book", job_id="old-job")
    assert repository.is_current_ingest(context, project_id="book", job_id="new-job")


def test_reclaimed_superseded_ingest_is_canceled_before_extraction(monkeypatch):
    job = {"id": "old-job", "lease_token": "lease", "input_payload": {"project_id": "book"}}
    canceled = []
    jobs = SimpleNamespace(
        claim_next=lambda *args, **kwargs: job,
        mark_running=lambda *args, **kwargs: job,
        request_cancel=lambda context, job_id: canceled.append(job_id),
        acknowledge_cancel=lambda *args, **kwargs: None,
    )

    @contextmanager
    def work(database):
        yield SimpleNamespace(jobs=jobs, connection=Connection(("new-job",)),
                              commit=lambda: None, rollback=lambda: None)

    monkeypatch.setattr("app.audiobook.worker.unit_of_work", work)
    assert run_ingest_once(None, None, local_tenant_context(), worker_id="recovery")
    assert canceled == ["old-job"]


def test_ingest_superseded_during_extraction_cannot_publish(monkeypatch):
    job = {"id": "old-job", "lease_token": "lease", "status": "running",
           "input_payload": {"project_id": "book", "source_asset_id": "source",
                             "source_format": "txt"}}
    connection = Connection(("old-job",))
    canceled = []
    jobs = SimpleNamespace(
        claim_next=lambda *args, **kwargs: job,
        mark_running=lambda *args, **kwargs: job,
        get_job=lambda *args, **kwargs: job,
        update_progress=lambda *args, **kwargs: None,
        renew_lease=lambda *args, **kwargs: None,
        request_cancel=lambda context, job_id: canceled.append(job_id),
        acknowledge_cancel=lambda *args, **kwargs: None,
    )

    @contextmanager
    def work(database):
        yield SimpleNamespace(jobs=jobs, connection=connection,
                              commit=lambda: None, rollback=lambda: None)

    def extract(**kwargs):
        # A newer request arrives after the early check and completes first.
        connection.current = ("new-job",)
        return SimpleNamespace(chapters=())

    monkeypatch.setattr("app.audiobook.worker.unit_of_work", work)
    monkeypatch.setattr("app.audiobook.worker.extract_source", extract)
    monkeypatch.setattr("app.audiobook.worker._reuse_existing_dialogue_segmentation",
                        lambda *args: SimpleNamespace(chapters=()))
    monkeypatch.setattr("app.audiobook.worker.local_structure_classifier", lambda: None)
    monkeypatch.setattr("app.audiobook.worker.analyze_document_structure", lambda *args, **kwargs: None)
    blobs = SimpleNamespace(read_bytes=lambda *args, **kwargs: b"source text")
    assert run_ingest_once(None, blobs, local_tenant_context(), worker_id="slow-worker")
    # No append_source_revision or complete method exists on the fakes: publishing
    # would fail this test instead of silently replacing the newer source.
    assert canceled == ["old-job"]
