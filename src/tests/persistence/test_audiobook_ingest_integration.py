from __future__ import annotations

import os
import base64
import io
import wave
from types import SimpleNamespace

import pytest

from app.audiobook.service import AudiobookService
from app.audiobook.worker import run_analyze_once, run_ingest_once
from app.audiobook.render_service import run_render_once
from app.audiobook.hashing import bytes_hash
from app.audiobook.review_repository import PostgresAudiobookReviewRepository
from app.persistence.blob_store import LocalBlobStore
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work


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
        assert run_analyze_once(database, context, worker_id="test:audiobook-analysis") is True
        detail = service.get_project(context, project["id"])
        assert detail["state"] == "review_required"
        assert len(detail["chapters"]) == 2
        assert detail["review_issues"]
        assert detail["speakers"][0]["kind"] == "narrator"
        assert all("".join(span["source_text"] for span in chapter["spans"]) == chapter["canonical_text"]
                   for chapter in detail["chapters"])
    finally:
        database.close()


def test_render_retry_reuses_checkpointed_audio(tmp_path, monkeypatch) -> None:
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-render-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Render Recovery")
        content = b'Chapter 1\n"Hello," said Nita. More words.'
        service.submit_source(context, project_id=project["id"], source_format="txt",
                              content=content, filename="render.txt")
        assert run_ingest_once(database, blobs, context, worker_id="test:ingest")
        assert run_analyze_once(database, context, worker_id="test:analyze")
        detail = service.get_project(context, project["id"])
        narrator = detail["speakers"][0]["id"]
        for issue in detail["review_issues"]:
            service.resolve_issue(context, project_id=project["id"], issue_id=issue["id"],
                                  speaker_id=narrator, role="dialogue")
        reference = tmp_path / "reference.wav"
        reference.write_bytes(b"stable voice profile")
        with unit_of_work(database) as work:
            PostgresAudiobookReviewRepository(work.connection).assign_voice(
                context, project_id=project["id"], speaker_id=narrator,
                voice_profile_id="voice-cloning:test", voice_revision_hash=bytes_hash(reference.read_bytes()),
            )
            work.commit()
        profile = SimpleNamespace(id="voice-cloning:test", storage_path=str(reference),
                                  metadata={"voice_clone_id": "test"})
        monkeypatch.setattr("app.audiobook.render_service.discover_canonical_voice_clone_assets", lambda: [profile])
        audio_buffer = io.BytesIO()
        with wave.open(audio_buffer, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16000)
            writer.writeframes(b"\x00\x00" * 1600)
        encoded = base64.b64encode(audio_buffer.getvalue()).decode()

        class Provider:
            calls = 0
            failed = False

            def generate_audio_batch(self, _requests):
                self.calls += 1
                if self.calls == 2 and not self.failed:
                    self.failed = True
                    raise RuntimeError("injected provider interruption")
                return [{"success": True, "audio": encoded}]

        provider = Provider()
        monkeypatch.setattr("app.audiobook.render_service.get_tts_provider", lambda _name: provider)
        service.start_render(context, project_id=project["id"], model_revision="test-model-revision")
        assert run_render_once(database, blobs, context, worker_id="test:render")
        assert run_render_once(database, blobs, context, worker_id="test:render")
        assert service.get_project(context, project["id"])["state"] == "rendered"
        with unit_of_work(database) as work:
            rendered = int(work.connection.execute(
                """
                SELECT count(*) FROM omnix_audiobook_renders AS r
                JOIN omnix_audiobook_spans AS s ON s.workspace_id = r.workspace_id AND s.id = r.span_id
                JOIN omnix_audiobook_chapters AS c ON c.workspace_id = s.workspace_id AND c.id = s.chapter_id
                JOIN omnix_audiobook_source_revisions AS sr ON sr.workspace_id = c.workspace_id AND sr.id = c.source_revision_id
                WHERE r.workspace_id = %s AND sr.project_id = %s
                """, (context.workspace_id, project["id"]),
            ).fetchone()[0])
            work.rollback()
        assert rendered == provider.calls - 1
    finally:
        database.close()
