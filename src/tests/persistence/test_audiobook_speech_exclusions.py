from __future__ import annotations

import os

import pytest

from app.audiobook.service import AudiobookService
from app.audiobook.worker import run_ingest_once
from app.persistence.blob_store import LocalBlobStore
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations, discover_migrations


def test_speech_exclusion_migration_binds_records_to_project_and_source_offsets():
    migration = next(item for item in discover_migrations() if item.version == "0094_audiobook_speech_exclusions")
    assert "FOREIGN KEY (workspace_id, project_id)" in migration.sql
    assert "chapter_hash" in migration.sql
    assert "CHECK (end_offset > start_offset)" in migration.sql


@pytest.mark.skipif(not os.environ.get("OMNIX_TEST_DATABASE_URL"), reason="OMNIX_TEST_DATABASE_URL is required")
def test_removal_is_local_durable_source_bound_and_reversible(tmp_path, monkeypatch):
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    monkeypatch.setattr("app.audiobook.worker.local_structure_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path)
        service = AudiobookService(database, blobs)
        book = service.create_project(context, title="Speech removal")
        text = "The morning began. Testing the first plan. Testing the next plan."
        service.submit_source(context, project_id=book["id"], source_format="txt", content=text.encode(), filename="book.txt")
        assert run_ingest_once(database, blobs, context, worker_id="test:remove-text")
        chapter_id = service.get_project(context, book["id"])["chapters"][0]["id"]
        chapter = service.get_chapter(context, project_id=book["id"], chapter_id=chapter_id)
        span = next(item for item in chapter["spans"] if "Testing" in item["source_text"])
        start = span["source_text"].index("Testing")
        with pytest.raises(ValueError, match="no longer matches"):
            service.exclude_span_text(context, project_id=book["id"], span_id=span["id"], start_offset=start, end_offset=start + 7, source_text="Wrong!!")
        excluded = service.exclude_span_text(context, project_id=book["id"], span_id=span["id"], start_offset=start, end_offset=start + 7, source_text="Testing")
        duplicate = service.exclude_span_text(context, project_id=book["id"], span_id=span["id"], start_offset=start, end_offset=start + 7, source_text="Testing")
        assert duplicate == excluded
        reopened = AudiobookService(database, blobs).get_chapter(context, project_id=book["id"], chapter_id=chapter_id)
        current = next(item for item in reopened["spans"] if item["id"] == span["id"])
        assert current["source_text"] == span["source_text"]
        assert current["speech_plan"]["tts_input_text"].count("Testing") == 1
        assert len(current["speech_exclusions"]) == 1
        service.restore_span_text(context, project_id=book["id"], exclusion_id=excluded["id"])
        restored = service.get_chapter(context, project_id=book["id"], chapter_id=chapter_id)
        assert next(item for item in restored["spans"] if item["id"] == span["id"])["speech_plan"]["hash"] == span["speech_plan"]["hash"]
    finally:
        database.close()
