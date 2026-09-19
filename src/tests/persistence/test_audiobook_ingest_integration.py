from __future__ import annotations

import os

import pytest

from app.audiobook.service import AudiobookService
from app.audiobook.worker import run_ingest_once
from app.persistence.blob_store import LocalBlobStore
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def test_durable_source_ingest_reconstructs_chapters_after_claim(tmp_path) -> None:
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-ingest-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path)
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="A Test Book")
        content = b'Chapter 1\n"Hello," said Nita.\nChapter 2\nMore words.'
        submission = service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=content, filename="test.txt",
        )
        assert submission["job_id"]
        assert run_ingest_once(database, blobs, context, worker_id="test:audiobook-ingest") is True
        detail = service.get_project(context, project["id"])
        assert detail["state"] == "extracted"
        assert len(detail["chapters"]) == 2
        assert all("".join(span["source_text"] for span in chapter["spans"]) == chapter["canonical_text"]
                   for chapter in detail["chapters"])
    finally:
        database.close()
