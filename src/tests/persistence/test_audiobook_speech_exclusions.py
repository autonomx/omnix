from __future__ import annotations

import os

import pytest

from app.apps.audiobook.service import AudiobookService
from app.apps.audiobook.worker import run_ingest_once
from app.persistence.blob_store import LocalBlobStore
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations, discover_migrations


def test_speech_exclusion_migration_binds_records_to_project_and_source_offsets():
    migration = next(item for item in discover_migrations() if item.version == "0094_audiobook_speech_exclusions")
    assert "FOREIGN KEY (workspace_id, project_id)" in migration.sql
    assert "chapter_hash" in migration.sql
    assert "CHECK (end_offset > start_offset)" in migration.sql


@pytest.mark.skipif(not os.environ.get("OMNIX_TEST_DATABASE_URL"), reason="OMNIX_TEST_DATABASE_URL is required")
def test_removal_is_local_durable_source_bound_and_reversible(tmp_path, monkeypatch):
    monkeypatch.setattr("app.apps.audiobook.worker.local_classifier", lambda: None)
    monkeypatch.setattr("app.apps.audiobook.worker.local_structure_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3))
    try:
        apply_migrations(database)
        context = ensure_local_identity(database)
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


@pytest.mark.skipif(not os.environ.get("OMNIX_TEST_DATABASE_URL"), reason="OMNIX_TEST_DATABASE_URL is required")
def test_removed_chapter_is_skipped_and_its_review_issues_stop_blocking(tmp_path, monkeypatch):
    from app.apps.audiobook.render_readiness import check_book_render_readiness
    from app.apps.audiobook.worker import run_analyze_once
    from app.persistence.unit_of_work import unit_of_work
    from uuid import uuid4

    monkeypatch.setattr("app.apps.audiobook.worker.local_classifier", lambda: None)
    monkeypatch.setattr("app.apps.audiobook.worker.local_structure_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3))
    try:
        apply_migrations(database)
        context = ensure_local_identity(database)
        blobs = LocalBlobStore(tmp_path)
        service = AudiobookService(database, blobs)
        book = service.create_project(context, title="Chapter removal")
        service.submit_source(context, project_id=book["id"], source_format="txt",
                              content=b'Chapter 1\n"Hello," said Nita.\nChapter 2\nMore words.', filename="book.txt")
        assert run_ingest_once(database, blobs, context, worker_id="test:remove-chapter")
        with unit_of_work(database) as work:
            revision = service.get_project(context, book["id"])["current_source_revision_id"]
            work.jobs.create_job(context, {
                "id": f"ab:test:classify:{uuid4().hex}", "module": "audiobook", "job_type": "audiobook.analyze",
                "resource_class": "cpu", "input_payload": {"project_id": book["id"], "source_revision_id": str(revision)},
            })
            work.commit()
        assert run_analyze_once(database, context, worker_id="test:remove-chapter-analysis")
        detail = service.get_project(context, book["id"])
        first, second = detail["chapters"]
        assert first["audio_removal_id"] is None
        issues_in_first = [issue for issue in detail["review_issues"] if issue["chapter_id"] == first["id"]]
        issues_elsewhere = [issue for issue in detail["review_issues"] if issue["chapter_id"] != first["id"]]
        assert issues_in_first and detail["state"] == "review_required"

        removal = service.remove_chapter_from_audio(context, project_id=book["id"], chapter_id=first["id"])
        assert service.remove_chapter_from_audio(context, project_id=book["id"], chapter_id=first["id"]) == removal
        removed = service.get_project(context, book["id"])
        assert removed["chapters"][0]["audio_removal_id"] == removal["id"]
        assert removed["chapters"][1]["audio_removal_id"] is None
        assert [issue["id"] for issue in removed["review_issues"]] == [issue["id"] for issue in issues_elsewhere]
        assert removed["state"] == ("review_required" if issues_elsewhere else "ready_to_render")
        chapter = service.get_chapter(context, project_id=book["id"], chapter_id=first["id"])
        assert "".join(span["source_text"] for span in chapter["spans"]) == chapter["canonical_text"]
        assert all(not span["speech_plan"]["tts_input_text"].strip() for span in chapter["spans"])
        with unit_of_work(database) as work:
            readiness = check_book_render_readiness(work.connection, context, project_id=book["id"], source_revision_id=revision)
            work.rollback()
        assert first["id"] in readiness.skipped_chapter_ids
        assert not any("open review issue" in blocker for blocker in readiness.blockers) or issues_elsewhere

        service.restore_span_text(context, project_id=book["id"], exclusion_id=removal["id"])
        restored = service.get_project(context, book["id"])
        assert restored["chapters"][0]["audio_removal_id"] is None
        assert {issue["id"] for issue in restored["review_issues"]} == {issue["id"] for issue in detail["review_issues"]}
        assert restored["state"] == "review_required"
        with pytest.raises(KeyError):
            service.remove_chapter_from_audio(context, project_id=book["id"], chapter_id="missing-chapter")
    finally:
        database.close()
