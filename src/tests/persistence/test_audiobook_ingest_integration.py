from __future__ import annotations

import os
import subprocess
import sys
import base64
import io
import wave
from pathlib import Path
from PIL import Image
from types import SimpleNamespace

import pytest

from app.audiobook.service import AudiobookService
from app.audiobook.worker import run_analyze_once, run_ingest_once
from app.audiobook.render_service import run_preview_once, run_render_once
from app.audiobook.assembly_service import run_assemble_once
from app.audiobook.render_cache import find_valid_render
from app.audiobook.render_planner import load_chapter_units
from app.audiobook.export_service import run_export_once
from app.audiobook import export_service
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


@pytest.fixture(autouse=True)
def _synthetic_tts_model_revision(monkeypatch) -> None:
    """These pipeline tests replace TTS; model artifact binding has separate tests."""
    monkeypatch.setattr("app.audiobook.service.assert_model_revision",
                        lambda _provider, _model, _revision: None)
    monkeypatch.setattr("app.audiobook.render_service.assert_model_revision",
                        lambda _provider, _model, _revision: None)


def test_durable_source_ingest_reconstructs_chapters_after_claim(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
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


def test_user_revises_span_without_changing_canonical_source(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-span-revision-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path)
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Revision Book")
        service.submit_source(context, project_id=project["id"], source_format="txt",
                              content=b"Chapter 1\nThe room was quiet.", filename="revision.txt")
        assert run_ingest_once(database, blobs, context, worker_id="test:revision-ingest")
        assert run_analyze_once(database, context, worker_id="test:revision-analyze")
        detail = service.get_project(context, project["id"])
        chapter = detail["chapters"][0]
        chapter_detail = service.get_chapter(context, project_id=project["id"], chapter_id=chapter["id"])
        original_text = chapter_detail["canonical_text"]
        span = next(item for item in chapter_detail["spans"] if item["annotation"])
        narrator = next(item for item in detail["speakers"] if item["kind"] == "narrator")
        for issue in detail["review_issues"]:
            service.resolve_issue(context, project_id=project["id"], issue_id=issue["id"],
                                  speaker_id=narrator["id"], role=issue["structural_kind"])
        with unit_of_work(database) as work:
            work.connection.execute(
                "UPDATE omnix_audiobook_projects SET state = 'exported' WHERE workspace_id = %s AND id = %s",
                (context.workspace_id, project["id"]),
            )
            work.commit()
        changed = service.revise_span(context, project_id=project["id"], span_id=span["id"],
                                      speaker_id=narrator["id"], role="narration",
                                      delivery="softly")
        assert changed["changed"] is True
        assert service.get_project(context, project["id"])["state"] == "ready_to_render"
        current = service.get_chapter(context, project_id=project["id"], chapter_id=chapter["id"])
        assert current["canonical_text"] == original_text
        assert "".join(item["source_text"] for item in current["spans"]) == original_text
        revised = next(item for item in current["spans"] if item["id"] == span["id"])
        assert revised["annotation"]["delivery"] == "softly"
        assert revised["annotation"]["revision"] == changed["revision"]
        assert service.revise_span(context, project_id=project["id"], span_id=span["id"],
                                   speaker_id=narrator["id"], role="narration",
                                   delivery="softly")["changed"] is False
    finally:
        database.close()


def test_local_classifier_proposes_unknown_speaker_without_rewriting_source(tmp_path, monkeypatch) -> None:
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-classifier-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path)
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Classifier Book")
        source = b'Chapter 1\n"I am here," said Nita.\nThe room was quiet.'
        service.submit_source(context, project_id=project["id"], source_format="txt",
                              content=source, filename="classifier.txt")
        assert run_ingest_once(database, blobs, context, worker_id="test:ingest-classifier")
        calls = []

        def classify(payload):
            calls.append(payload)
            return {"span_id": payload["span_id"],
                    "speaker": "Nita" if payload["source_text"].lstrip().startswith('"') else "Narrator",
                    "role": "dialogue" if payload["source_text"].lstrip().startswith('"') else "narration",
                    "delivery": "quiet"}

        monkeypatch.setattr("app.audiobook.worker.local_classifier",
                            lambda: (classify, {"mode": "local_llm_classifier", "provider_id": "test"}))
        assert run_analyze_once(database, context, worker_id="test:analyze-classifier")
        detail = service.get_project(context, project["id"])
        assert "".join(span["source_text"] for span in detail["chapters"][0]["spans"]) == detail["chapters"][0]["canonical_text"]
        assert any(issue["speaker_candidate"] == "Nita" and issue["reason"] == "UNSUPPORTED_SPEAKER"
                   for issue in detail["review_issues"])
        assert all("source_text" in call and "span_id" in call for call in calls)
        nita = service.add_speaker(context, project_id=project["id"], canonical_name="Nita")
        service.confirm_alias(context, project_id=project["id"], speaker_id=nita["id"], alias="Nita Sr.")
        assert "Nita Sr." in next(item for item in service.get_project(context, project["id"])["speakers"]
                                  if item["id"] == nita["id"])["aliases"]
        with pytest.raises(ValueError, match="another speaker"):
            service.confirm_alias(context, project_id=project["id"], speaker_id=detail["speakers"][0]["id"],
                                  alias="Nita")
    finally:
        database.close()


def test_public_domain_epub_golden_book_reaches_verified_m4b(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-golden-book-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="The Yellow Wallpaper",
                                         author="Charlotte Perkins Gilman")
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "audiobook" / "yellow_wallpaper_gutenberg_1952.epub"
        service.submit_source(context, project_id=project["id"], source_format="epub",
                              content=fixture.read_bytes(), filename=fixture.name)
        assert run_ingest_once(database, blobs, context, worker_id="test:golden-ingest")
        assert run_analyze_once(database, context, worker_id="test:golden-analysis")
        detail = service.get_project(context, project["id"])
        assert sum(len(chapter["spans"]) for chapter in detail["chapters"]) == 44
        compact = service.get_project(context, project["id"], include_text=False)
        assert "canonical_text" not in compact["chapters"][0]
        chapter_detail = service.get_chapter(context, project_id=project["id"],
                                             chapter_id=detail["chapters"][0]["id"])
        assert chapter_detail["canonical_text"] == detail["chapters"][0]["canonical_text"]
        assert "speech_plan" in chapter_detail["spans"][0]
        assert "annotation" in chapter_detail["spans"][0]
        narrator = detail["speakers"][0]["id"]
        for issue in detail["review_issues"]:
            service.resolve_issue(context, project_id=project["id"], issue_id=issue["id"],
                                  speaker_id=narrator, role=issue["structural_kind"])
        reference = tmp_path / "narrator.wav"
        reference.write_bytes(b"golden narrator reference")
        with unit_of_work(database) as work:
            PostgresAudiobookReviewRepository(work.connection).assign_voice(
                context, project_id=project["id"], speaker_id=narrator,
                voice_profile_id="voice-cloning:golden",
                voice_revision_hash=bytes_hash(reference.read_bytes()),
            )
            work.commit()
        profile = SimpleNamespace(id="voice-cloning:golden", storage_path=str(reference),
                                  metadata={"voice_clone_id": "golden"})
        monkeypatch.setattr("app.audiobook.render_service.discover_canonical_voice_clone_assets",
                            lambda: [profile])
        audio_buffer = io.BytesIO()
        with wave.open(audio_buffer, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16000)
            writer.writeframes(b"\xe8\x03\x18\xfc" * 800)
        encoded = base64.b64encode(audio_buffer.getvalue()).decode()

        class GoldenProvider:
            calls = 0

            def generate_audio_batch(self, requests):
                self.calls += len(requests)
                return [{"success": True, "audio": encoded} for _ in requests]

        provider = GoldenProvider()
        monkeypatch.setattr("app.audiobook.render_service.get_tts_provider", lambda _name: provider)
        service.start_render(context, project_id=project["id"], model_revision="golden-model-revision")
        child_code = """
import os, sys
from types import SimpleNamespace
from app.audiobook import render_service as render
from app.persistence.blob_store import LocalBlobStore
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant

class Provider:
    def generate_audio_batch(self, requests):
        return [{"success": True, "audio": sys.argv[4]} for _ in requests]

render.get_tts_provider = lambda _name: Provider()
render.assert_model_revision = lambda _provider, _model, _revision: None
render.discover_canonical_voice_clone_assets = lambda: [
    SimpleNamespace(id="voice-cloning:golden", storage_path=sys.argv[3], metadata={})]
original = render._save_render
def crash_after_checkpoint(*args, **kwargs):
    original(*args, **kwargs)
    os._exit(137)
render._save_render = crash_after_checkpoint
database = PostgresDatabase(DatabaseSettings(url=sys.argv[1], pool_min=1, pool_max=2,
    connect_timeout_seconds=10, statement_timeout_ms=30000, lock_timeout_ms=5000,
    application_name="omnix-audiobook-golden-crash-test"))
render.run_render_once(database, LocalBlobStore(sys.argv[2]), bootstrap_local_tenant(database),
                       worker_id="test:golden-crashed-worker")
"""
        child_env = os.environ.copy()
        child_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        crashed = subprocess.run(
            [sys.executable, "-c", child_code, os.environ["OMNIX_TEST_DATABASE_URL"],
             str(blobs.root), str(reference), encoded],
            env=child_env, capture_output=True, text=True, timeout=40,
        )
        assert crashed.returncode == 137, crashed.stderr
        with unit_of_work(database) as work:
            checkpoint = work.connection.execute(
                """SELECT b.completed_keys, j.id FROM omnix_audiobook_render_batches b
                    JOIN omnix_jobs j ON j.id = b.job_id
                   WHERE b.workspace_id = %s AND j.status = 'running'
                     AND j.input_payload->>'project_id' = %s""",
                (context.workspace_id, project["id"]),
            ).fetchone()
            assert checkpoint and len(checkpoint[0]) == 1
            work.connection.execute(
                """UPDATE omnix_jobs SET lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, checkpoint[1]),
            )
            work.commit()
        assert run_render_once(database, blobs, context, worker_id="test:golden-render")
        assert run_render_once(database, blobs, context, worker_id="test:golden-render")
        assert provider.calls == 43
        with unit_of_work(database) as work:
            diagnostics = work.connection.execute(
                """SELECT diagnostics FROM omnix_audiobook_renders r
                     JOIN omnix_audiobook_spans s ON s.id = r.span_id AND s.workspace_id = r.workspace_id
                     JOIN omnix_audiobook_chapters c ON c.id = s.chapter_id AND c.workspace_id = s.workspace_id
                    WHERE r.workspace_id = %s AND c.source_revision_id = %s LIMIT 1""",
                (context.workspace_id, detail["current_source_revision_id"]),
            ).fetchone()[0]
            work.rollback()
        assert diagnostics["generation_wall_seconds"] >= 0
        assert diagnostics["real_time_factor"] >= 0
        assert diagnostics["batch_size"] == 1
        assert run_assemble_once(database, blobs, context, worker_id="test:golden-assemble")
        assert run_assemble_once(database, blobs, context, worker_id="test:golden-assemble")
        assert service.get_project(context, project["id"])["state"] == "ready_to_export"
        if os.environ.get("OMNIX_TEST_FFMPEG"):
            monkeypatch.setenv("OMNIX_FFMPEG", os.environ["OMNIX_TEST_FFMPEG"])
            service.start_export(context, project_id=project["id"], format="m4b")
            assert run_export_once(database, blobs, context, worker_id="test:golden-export")
            exported = service.list_exports(context, project["id"])[0]
            report = service.export_report(context, project_id=project["id"],
                                           export_id=exported["id"])
            assert report["passed"] is True
            assert len(report["render_details"]) == 44
            assert report["generation_summary"]["render_count"] == 44
            assert report["generation_summary"]["audio_duration_seconds"] > 0
            assert report["manifest"]["source_revision_id"] == detail["current_source_revision_id"]
    finally:
        database.close()


def test_long_chapter_uses_one_durable_render_job_and_checkpoints_every_unit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-endurance-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Long chapter")
        text = "Chapter 1\n" + "".join(
            f'"Paragraph {index} has a spoken sentence." The narrator continued.\n'
            for index in range(150)
        )
        service.submit_source(context, project_id=project["id"], source_format="txt",
                              content=text.encode(), filename="long.txt")
        assert run_ingest_once(database, blobs, context, worker_id="test:long-ingest")
        assert run_analyze_once(database, context, worker_id="test:long-analyze")
        detail = service.get_project(context, project["id"])
        assert len(detail["chapters"]) == 1
        assert len(detail["chapters"][0]["spans"]) >= 300
        narrator = next(item for item in detail["speakers"] if item["kind"] == "narrator")
        for issue in detail["review_issues"]:
            service.resolve_issue(context, project_id=project["id"], issue_id=issue["id"],
                                  speaker_id=narrator["id"], role=issue["structural_kind"])
        reference = tmp_path / "narrator.wav"
        reference.write_bytes(b"long-book narrator voice")
        with unit_of_work(database) as work:
            PostgresAudiobookReviewRepository(work.connection).assign_voice(
                context, project_id=project["id"], speaker_id=narrator["id"],
                voice_profile_id="voice-cloning:long", voice_revision_hash=bytes_hash(reference.read_bytes()),
            )
            work.commit()
        profile = SimpleNamespace(id="voice-cloning:long", storage_path=str(reference), metadata={})
        monkeypatch.setattr("app.audiobook.render_service.discover_canonical_voice_clone_assets",
                            lambda: [profile])
        audio_buffer = io.BytesIO()
        with wave.open(audio_buffer, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16000)
            writer.writeframes(b"\xe8\x03\x18\xfc" * 80)
        encoded = base64.b64encode(audio_buffer.getvalue()).decode()

        class Provider:
            calls = 0

            def generate_audio_batch(self, requests):
                self.calls += len(requests)
                return [{"success": True, "audio": encoded} for _ in requests]

        provider = Provider()
        monkeypatch.setattr("app.audiobook.render_service.get_tts_provider", lambda _name: provider)
        service.start_render(context, project_id=project["id"], model_revision="long-test-model")
        assert run_render_once(database, blobs, context, worker_id="test:long-render")
        with unit_of_work(database) as work:
            render_jobs = work.connection.execute(
                """SELECT count(*) FROM omnix_jobs WHERE workspace_id = %s
                     AND module = 'audiobook' AND job_type = 'audiobook.render-chapter'
                     AND input_payload->>'project_id' = %s""",
                (context.workspace_id, project["id"]),
            ).fetchone()[0]
            checkpoints = work.connection.execute(
                """SELECT jsonb_array_length(completed_keys) FROM omnix_audiobook_render_batches b
                     JOIN omnix_jobs j ON j.id = b.job_id
                    WHERE b.workspace_id = %s AND j.input_payload->>'project_id' = %s""",
                (context.workspace_id, project["id"]),
            ).fetchone()[0]
            work.rollback()
        assert render_jobs == 1
        assert checkpoints == provider.calls >= 300
        assert run_assemble_once(database, blobs, context, worker_id="test:long-assemble")
        assert service.get_project(context, project["id"])["state"] == "ready_to_export"
    finally:
        database.close()


def test_render_retry_reuses_checkpointed_audio(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
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
        content = b'Chapter 1\n"Hello," said Nita. More words.\nChapter 2\nThe next chapter begins.'
        service.submit_source(context, project_id=project["id"], source_format="txt",
                              content=content, filename="render.txt")
        assert run_ingest_once(database, blobs, context, worker_id="test:ingest")
        assert run_analyze_once(database, context, worker_id="test:analyze")
        detail = service.get_project(context, project["id"])
        narrator = detail["speakers"][0]["id"]
        nita = service.add_speaker(context, project_id=project["id"], canonical_name="Nita")["id"]
        for issue in detail["review_issues"]:
            service.resolve_issue(context, project_id=project["id"], issue_id=issue["id"],
                                  speaker_id=nita if issue["structural_kind"] == "dialogue" else narrator,
                                  role=issue["structural_kind"])
        reference = tmp_path / "reference.wav"
        reference.write_bytes(b"stable voice profile")
        nita_reference = tmp_path / "nita.wav"
        nita_reference.write_bytes(b"Nita voice version one")
        with unit_of_work(database) as work:
            review = PostgresAudiobookReviewRepository(work.connection)
            review.assign_voice(
                context, project_id=project["id"], speaker_id=narrator,
                voice_profile_id="voice-cloning:test", voice_revision_hash=bytes_hash(reference.read_bytes()),
            )
            work.commit()
        narrator_chapter = next(chapter for chapter in detail["chapters"]
                                if any(span["structural_kind"] == "narration" for span in chapter["spans"]))
        narrator_span = next(span for span in narrator_chapter["spans"]
                             if span["structural_kind"] == "narration")
        audition = service.start_preview(
            context, project_id=project["id"], chapter_id=narrator_chapter["id"],
            span_id=narrator_span["id"], model_revision="test-model-revision",
        )
        with unit_of_work(database) as work:
            work.jobs.request_cancel(context, audition["job_id"])
            work.commit()
        with unit_of_work(database) as work:
            review = PostgresAudiobookReviewRepository(work.connection)
            review.assign_voice(
                context, project_id=project["id"], speaker_id=nita,
                voice_profile_id="voice-cloning:nita", voice_revision_hash=bytes_hash(nita_reference.read_bytes()),
            )
            work.commit()
        profile = SimpleNamespace(id="voice-cloning:test", storage_path=str(reference),
                                  metadata={"voice_clone_id": "test"})
        nita_profile = SimpleNamespace(id="voice-cloning:nita", storage_path=str(nita_reference),
                                       metadata={"voice_clone_id": "nita"})
        monkeypatch.setattr("app.audiobook.render_service.discover_canonical_voice_clone_assets",
                            lambda: [profile, nita_profile])
        audio_buffer = io.BytesIO()
        with wave.open(audio_buffer, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16000)
            writer.writeframes(b"\xe8\x03\x18\xfc" * 800)
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
        with pytest.raises(ValueError, match="does not apply generation seeds"):
            service.start_render(context, project_id=project["id"],
                                 model_revision="test-model-revision", seed=42)
        submission = service.start_render(context, project_id=project["id"], model_revision="test-model-revision")
        assert submission["chapter_count"] == 2
        for _ in range(8):
            if service.get_project(context, project["id"])["state"] == "mastering":
                break
            assert run_render_once(database, blobs, context, worker_id="test:render")
        assert service.get_project(context, project["id"])["state"] == "mastering"
        with unit_of_work(database) as work:
            for chapter in service.get_project(context, project["id"])["chapters"]:
                for unit in load_chapter_units(work.connection, context,
                                               project_id=project["id"], chapter_id=chapter["id"]):
                    key = unit.identity(provider_id="faster-qwen3-tts", model_id="Qwen3-TTS",
                                        model_revision="test-model-revision",
                                        generation_parameters={}, seed=None).key()
                    assert find_valid_render(work.connection, context, blobs, key), (unit.span_id, key)
            work.rollback()
        first_chapter = service.get_project(context, project["id"])["chapters"][0]
        first_span = first_chapter["spans"][0]
        with pytest.raises(ValueError, match="does not apply generation seeds"):
            service.start_preview(context, project_id=project["id"],
                                  chapter_id=first_chapter["id"], span_id=first_span["id"],
                                  model_revision="test-model-revision", seed=42)
        calls_before_preview = provider.calls
        cached_preview = service.start_preview(
            context, project_id=project["id"], chapter_id=first_chapter["id"],
            span_id=first_span["id"], model_revision="test-model-revision",
        )
        assert run_preview_once(database, blobs, context, worker_id="test:preview")
        assert provider.calls == calls_before_preview
        assert service.read_preview(context, project_id=project["id"],
                                    job_id=cached_preview["job_id"]) == audio_buffer.getvalue()
        revised_preview = service.start_preview(
            context, project_id=project["id"], chapter_id=first_chapter["id"],
            span_id=first_span["id"], model_revision="test-model-revision",
            generation_parameters={"temperature": 0.7},
        )
        assert run_preview_once(database, blobs, context, worker_id="test:preview")
        assert provider.calls == calls_before_preview + 1
        assert service.read_preview(context, project_id=project["id"],
                                    job_id=revised_preview["job_id"]) == audio_buffer.getvalue()
        with pytest.raises(KeyError):
            service.read_preview(context, project_id="other-project",
                                 job_id=revised_preview["job_id"])
        assert run_assemble_once(database, blobs, context, worker_id="test:assemble")
        assert run_assemble_once(database, blobs, context, worker_id="test:assemble")
        assert service.get_project(context, project["id"])["state"] == "ready_to_export"
        with unit_of_work(database) as work:
            rendered = int(work.connection.execute(
                """
                SELECT count(*) FROM omnix_audiobook_renders AS r
                JOIN omnix_jobs AS j ON j.id = r.diagnostics->>'job_id'
                     AND j.workspace_id = r.workspace_id
                JOIN omnix_audiobook_spans AS s ON s.workspace_id = r.workspace_id AND s.id = r.span_id
                JOIN omnix_audiobook_chapters AS c ON c.workspace_id = s.workspace_id AND c.id = s.chapter_id
                JOIN omnix_audiobook_source_revisions AS sr ON sr.workspace_id = c.workspace_id AND sr.id = c.source_revision_id
                WHERE r.workspace_id = %s AND sr.project_id = %s
                  AND j.job_type = 'audiobook.render-chapter'
                """, (context.workspace_id, project["id"]),
            ).fetchone()[0])
            work.rollback()
        assert rendered == provider.calls - 2  # one failed call and one new preview
        real_ffmpeg_binary = export_service.ffmpeg_binary
        real_ffmpeg_version = export_service.ffmpeg_version
        real_popen = subprocess.Popen
        monkeypatch.setattr("app.audiobook.export_service.ffmpeg_binary", lambda: "test-ffmpeg")
        monkeypatch.setattr("app.audiobook.export_service.ffmpeg_version", lambda _binary: "test-ffmpeg 1")

        class FakeEncoder:
            def __init__(self, command, **_kwargs):
                Path(command[-1]).write_bytes(Path(command[command.index("-i") + 1]).read_bytes())

            def wait(self, timeout=None):
                return 0

            def poll(self):
                return 0

        monkeypatch.setattr("app.audiobook.export_service.subprocess.Popen", FakeEncoder)
        submission = service.start_export(context, project_id=project["id"], format="wav")
        assert run_export_once(database, blobs, context, worker_id="test:export")
        exports = service.list_exports(context, project["id"])
        assert len(exports) == 1
        output, mime, format = service.read_export(context, project_id=project["id"],
                                                   export_id=exports[0]["id"])
        stream, stream_mime, stream_format = service.open_export(
            context, project_id=project["id"], export_id=exports[0]["id"])
        with stream:
            assert stream.read(16) == output[:16]
        assert (stream_mime, stream_format) == (mime, format)
        assert output.startswith(b"RIFF")
        assert mime == "audio/wav" and format == "wav"
        assert service.get_project(context, project["id"])["state"] == "exported"
        report = service.export_report(context, project_id=project["id"], export_id=exports[0]["id"])
        assert report["passed"] is True
        assert len(report["manifest"]["chapters"]) == 2
        assert len(report["render_details"]) == rendered
        with unit_of_work(database) as work:
            manifest = work.connection.execute(
                "SELECT manifest FROM omnix_audiobook_export_manifests WHERE workspace_id = %s AND id = %s",
                (context.workspace_id, submission["manifest_id"]),
            ).fetchone()[0]
            work.rollback()
        assert manifest["source_revision_id"] == service.get_project(context, project["id"])["current_source_revision_id"]
        assert len(manifest["chapters"]) == 2
        assert sum(len(chapter["renders"]) for chapter in manifest["chapters"]) == rendered
        cover_bytes = io.BytesIO()
        Image.new("RGB", (8, 8), (80, 40, 120)).save(cover_bytes, format="PNG")
        service.set_cover(context, project_id=project["id"], content=cover_bytes.getvalue(), filename="cover.png")
        assert service.read_cover(context, project_id=project["id"]) == (cover_bytes.getvalue(), "image/png")
        assert service.get_project(context, project["id"])["state"] == "ready_to_export"
        new_submission = service.start_export(context, project_id=project["id"], format="wav")
        assert new_submission["manifest_hash"] != submission["manifest_hash"]
        assert run_export_once(database, blobs, context, worker_id="test:export")
        assert len(service.list_exports(context, project["id"])) == 2
        assert provider.calls - 2 == rendered
        if os.environ.get("OMNIX_TEST_FFMPEG"):
            monkeypatch.setenv("OMNIX_FFMPEG", os.environ["OMNIX_TEST_FFMPEG"])
            monkeypatch.setattr(export_service, "ffmpeg_binary", real_ffmpeg_binary)
            monkeypatch.setattr(export_service, "ffmpeg_version", real_ffmpeg_version)
            monkeypatch.setattr(export_service.subprocess, "Popen", real_popen)
            for codec in ("m4b", "flac", "wav", "mp3"):
                service.start_export(context, project_id=project["id"], format=codec)
                assert run_export_once(database, blobs, context, worker_id="test:export")
                latest = service.list_exports(context, project["id"])[0]
                data, _mime, actual_format = service.read_export(
                    context, project_id=project["id"], export_id=latest["id"])
                assert actual_format == codec and len(data) > 100
                output_path = tmp_path / f"encoded.{codec}"
                output_path.write_bytes(data)
                probe = subprocess.run([os.environ["OMNIX_TEST_FFMPEG"], "-i", str(output_path)],
                                       capture_output=True, text=True, timeout=30)
                assert "Duration:" in probe.stderr
                if codec == "m4b":
                    assert probe.stderr.count("Chapter #") >= 2
                    assert "Render Recovery" in probe.stderr
        prior_calls = provider.calls
        nita_reference.write_bytes(b"Nita voice version two")
        with unit_of_work(database) as work:
            PostgresAudiobookReviewRepository(work.connection).assign_voice(
                context, project_id=project["id"], speaker_id=nita,
                voice_profile_id="voice-cloning:nita",
                voice_revision_hash=bytes_hash(nita_reference.read_bytes()),
            )
            affected_spans = int(work.connection.execute(
                """SELECT count(*) FROM omnix_audiobook_spans s
                   JOIN omnix_audiobook_chapters c ON c.id = s.chapter_id
                   JOIN omnix_audiobook_source_revisions sr ON sr.id = c.source_revision_id
                   JOIN LATERAL (SELECT speaker_id FROM omnix_audiobook_annotations a
                                  WHERE a.span_id = s.id ORDER BY revision DESC LIMIT 1) a ON TRUE
                  WHERE sr.project_id = %s AND a.speaker_id = %s::uuid""",
                (project["id"], nita),
            ).fetchone()[0])
            work.commit()
        assert affected_spans > 0
        assert service.get_project(context, project["id"])["state"] == "ready_to_render"
        service.start_render(context, project_id=project["id"], model_revision="test-model-revision")
        for _ in range(4):
            if service.get_project(context, project["id"])["state"] == "mastering":
                break
            assert run_render_once(database, blobs, context, worker_id="test:render")
        assert service.get_project(context, project["id"])["state"] == "mastering"
        assert provider.calls - prior_calls == affected_spans
        assert run_assemble_once(database, blobs, context, worker_id="test:assemble")
        assert run_assemble_once(database, blobs, context, worker_id="test:assemble")
        assert service.get_project(context, project["id"])["state"] == "ready_to_export"
        monkeypatch.setattr(export_service.subprocess, "Popen", real_popen)
        service.set_pronunciation(context, project_id=project["id"],
                                  source_term="Chapter", spoken_term="Chappter")
        calls_before_restart = provider.calls
        restarted_run = service.start_render(context, project_id=project["id"],
                                             model_revision="test-model-revision")
        child_code = """
import os, sys
from types import SimpleNamespace
from app.audiobook import render_service as render
from app.persistence.blob_store import LocalBlobStore
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant

class Provider:
    def generate_audio_batch(self, requests):
        return [{"success": True, "audio": sys.argv[5]} for _ in requests]

render.get_tts_provider = lambda _name: Provider()
render.assert_model_revision = lambda _provider, _model, _revision: None
render.discover_canonical_voice_clone_assets = lambda: [
    SimpleNamespace(id="voice-cloning:test", storage_path=sys.argv[3], metadata={"voice_clone_id": "test"}),
    SimpleNamespace(id="voice-cloning:nita", storage_path=sys.argv[4], metadata={"voice_clone_id": "nita"}),
]
original = render._save_render
def crash_after_checkpoint(*args, **kwargs):
    original(*args, **kwargs)
    os._exit(137)
render._save_render = crash_after_checkpoint
database = PostgresDatabase(DatabaseSettings(url=sys.argv[1], pool_min=1, pool_max=2,
    connect_timeout_seconds=10, statement_timeout_ms=30000, lock_timeout_ms=5000,
    application_name="omnix-audiobook-crash-test"))
render.run_render_once(database, LocalBlobStore(sys.argv[2]), bootstrap_local_tenant(database),
                       worker_id="test:crashed-worker")
"""
        child_env = os.environ.copy()
        child_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        crashed = subprocess.run(
            [sys.executable, "-c", child_code, os.environ["OMNIX_TEST_DATABASE_URL"],
             str(blobs.root), str(reference), str(nita_reference), encoded],
            env=child_env, capture_output=True, text=True, timeout=40,
        )
        assert crashed.returncode == 137, crashed.stderr
        with unit_of_work(database) as work:
            checkpoint = work.connection.execute(
                """SELECT b.completed_keys, j.id FROM omnix_audiobook_render_batches b
                    JOIN omnix_jobs j ON j.id = b.job_id
                   WHERE b.workspace_id = %s
                     AND j.input_payload->>'render_run_id' = %s
                     AND j.status = 'running'""",
                (context.workspace_id, restarted_run["render_run_id"]),
            ).fetchone()
            assert checkpoint and len(checkpoint[0]) == 1
            missing_after_crash = 0
            for chapter in service.get_project(context, project["id"])["chapters"]:
                for unit in load_chapter_units(work.connection, context,
                                               project_id=project["id"], chapter_id=chapter["id"]):
                    key = unit.identity(provider_id="faster-qwen3-tts", model_id="Qwen3-TTS",
                                        model_revision="test-model-revision",
                                        generation_parameters={}, seed=None).key()
                    if find_valid_render(work.connection, context, blobs, key) is None:
                        missing_after_crash += 1
            work.connection.execute(
                """UPDATE omnix_jobs SET lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'
                    WHERE workspace_id = %s AND id = %s AND status = 'running'""",
                (context.workspace_id, checkpoint[1]),
            )
            work.commit()
        for _ in range(5):
            if service.get_project(context, project["id"])["state"] == "mastering":
                break
            assert run_render_once(database, blobs, context, worker_id="test:render-recovered")
        assert service.get_project(context, project["id"])["state"] == "mastering"
        assert provider.calls - calls_before_restart == missing_after_crash
        with unit_of_work(database) as work:
            reused = int(work.connection.execute(
                "SELECT count(*) FROM omnix_audiobook_renders WHERE workspace_id = %s AND render_key = %s",
                (context.workspace_id, checkpoint[0][0]),
            ).fetchone()[0])
            work.rollback()
        assert reused == 1
        assert run_assemble_once(database, blobs, context, worker_id="test:assemble")
        assert run_assemble_once(database, blobs, context, worker_id="test:assemble")
        assert service.get_project(context, project["id"])["state"] == "ready_to_export"
        old_export_id = exports[0]["id"]
        assert service.export_report(context, project_id=project["id"], export_id=old_export_id)["passed"]
        with unit_of_work(database) as work:
            render_asset = work.connection.execute(
                """SELECT a.storage_key FROM omnix_audiobook_renders r
                   JOIN omnix_assets a ON a.id = r.audio_asset_id
                  WHERE r.workspace_id = %s AND r.id = %s""",
                (context.workspace_id, manifest["chapters"][0]["render_ids"][0]),
            ).fetchone()[0]
            work.rollback()
        blobs.put_bytes(render_asset, b"corrupted render data")
        damaged = service.export_report(context, project_id=project["id"], export_id=old_export_id)
        assert damaged["passed"] is False
        assert any(item["kind"] == "span_render" for item in damaged["failed_checks"])
    finally:
        database.close()
