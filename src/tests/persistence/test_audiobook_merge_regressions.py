"""Durable regression coverage for source fencing and legacy export ownership."""
import base64
import io
import os
import wave
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.audiobook.service import AudiobookService
from app.audiobook.render_planner import load_chapter_units
from app.audiobook.render_service import run_preview_once
from app.audiobook.worker import run_ingest_once
from app.persistence.blob_store import LocalBlobStore
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations, discover_migrations
from app.persistence.unit_of_work import unit_of_work


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    monkeypatch.setattr("app.audiobook.worker.local_structure_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-merge-regressions",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path)
        yield database, context, blobs, AudiobookService(database, blobs)
    finally:
        database.close()


def test_reclaimed_ingest_cannot_rewind_completed_newer_source(pipeline):
    database, context, blobs, service = pipeline
    project_id = service.create_project(context, title="Ingest fencing")["id"]
    older = service.submit_source(context, project_id=project_id, source_format="txt",
                                  content=b"Old source.", filename="old.txt")
    with unit_of_work(database) as work:
        claimed = work.jobs.claim_next(context, worker_id="crashed-ingest",
                                       resource_classes=["cpu"], job_types=["audiobook.ingest"],
                                       lease_seconds=3600)
        assert claimed["id"] == older["job_id"]
        work.jobs.mark_running(context, job_id=claimed["id"], worker_id="crashed-ingest",
                               lease_token=claimed["lease_token"])
        work.commit()
    newer = service.submit_source(context, project_id=project_id, source_format="txt",
                                  content=b"New source.", filename="new.txt")
    assert run_ingest_once(database, blobs, context, worker_id="new-ingest")
    current_revision = service.get_project(context, project_id)["current_source_revision_id"]
    with unit_of_work(database) as work:
        assert work.jobs.get_job(context, newer["job_id"])["status"] == "completed"
        work.connection.execute(
            "UPDATE omnix_jobs SET lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second' WHERE id = %s",
            (older["job_id"],),
        )
        work.commit()
    assert run_ingest_once(database, blobs, context, worker_id="recovered-ingest")
    assert service.get_project(context, project_id)["current_source_revision_id"] == current_revision
    with unit_of_work(database) as work:
        assert work.jobs.get_job(context, older["job_id"])["status"] == "canceled"
        work.rollback()


def test_export_ownership_backfill_allows_cancel_and_project_deletion(pipeline):
    database, context, blobs, service = pipeline
    project_id = service.create_project(context, title="Export ownership")["id"]
    service.submit_source(context, project_id=project_id, source_format="txt",
                          content=b"Exportable source.", filename="source.txt")
    assert run_ingest_once(database, blobs, context, worker_id="export-source")
    revision_id = service.get_project(context, project_id)["current_source_revision_id"]
    job_ids = []
    with unit_of_work(database) as work:
        for _ in range(2):
            job_id, manifest_id = f"ab:export:{uuid4().hex}", f"ab:manifest:{uuid4().hex}"
            work.jobs.create_job(context, {
                "id": job_id, "module": "audiobook", "job_type": "audiobook.export",
                "resource_class": "cpu", "input_payload": {"manifest_id": manifest_id},
            })
            work.connection.execute(
                """INSERT INTO omnix_audiobook_export_manifests
                    (id, workspace_id, project_id, source_revision_id, job_id,
                     format, manifest, manifest_hash)
                    VALUES (%s, %s, %s, %s, %s, 'wav', '{}'::jsonb, %s)""",
                (manifest_id, context.workspace_id, project_id, revision_id, job_id, "a" * 64),
            )
            job_ids.append(job_id)
        migration = next(item for item in discover_migrations()
                         if item.version == "0095_audiobook_export_job_ownership")
        work.connection.execute(migration.sql)
        work.connection.execute(migration.sql)  # Backfill remains idempotent.
        for job_id in job_ids:
            assert work.jobs.get_job(context, job_id)["input_payload"]["project_id"] == project_id
        work.commit()
    with pytest.raises(KeyError):
        service.cancel_job(context, project_id="another-project", job_id=job_ids[0])
    assert service.cancel_job(context, project_id=project_id,
                              job_id=job_ids[0])["cancellation_requested"]
    service.delete_project(context, project_id=project_id)
    with unit_of_work(database) as work:
        assert all(work.jobs.get_job(context, job_id)["status"] == "canceled" for job_id in job_ids)
        work.rollback()


def test_long_span_audition_uses_selected_voice_and_returns_all_segments(pipeline, monkeypatch, tmp_path):
    database, context, blobs, service = pipeline
    monkeypatch.setattr("app.audiobook.service.assert_model_revision", lambda *args: None)
    monkeypatch.setattr("app.audiobook.render_service.assert_model_revision", lambda *args: None)
    project_id = service.create_project(context, title="Full span audition")["id"]
    service.submit_source(context, project_id=project_id, source_format="txt",
                          content=("A long sentence for the audition. " * 40).encode(), filename="long.txt")
    assert run_ingest_once(database, blobs, context, worker_id="audition-source")
    project = service.get_project(context, project_id)
    chapter_id = project["chapters"][0]["id"]
    span_id = service.get_chapter(context, project_id=project_id,
                                  chapter_id=chapter_id)["spans"][0]["id"]
    narrator_id = next(item["id"] for item in project["speakers"] if item["kind"] == "narrator")
    service.revise_span(context, project_id=project_id, span_id=span_id,
                        speaker_id=narrator_id, role="narration")
    profiles = []
    for name in ("saved", "candidate"):
        reference = tmp_path / f"{name}.wav"
        reference.write_bytes(name.encode())
        profiles.append(SimpleNamespace(id=f"voice-cloning:{name}", storage_path=str(reference), metadata={}))
    monkeypatch.setattr("app.audiobook.service.discover_canonical_voice_clone_assets", lambda: profiles)
    monkeypatch.setattr("app.audiobook.render_service.discover_canonical_voice_clone_assets", lambda: profiles)
    service.assign_voice(context, project_id=project_id, speaker_id=narrator_id,
                          voice_profile_id="voice-cloning:saved")
    with unit_of_work(database) as work:
        expected_texts = [unit.speech_plan.tts_input_text.strip() for unit in load_chapter_units(
            work.connection, context, project_id=project_id, chapter_id=chapter_id, span_id=span_id,
        )]
        work.rollback()
    assert len(expected_texts) > 1
    calls = []

    def generate(requests):
        calls.extend(requests)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16000)
            writer.writeframes(b"\x01\x00" * 160)
        return [{"success": True, "audio": base64.b64encode(buffer.getvalue()).decode()}]

    monkeypatch.setattr("app.audiobook.render_service.get_tts_provider",
                        lambda *args: SimpleNamespace(generate_audio_batch=generate))
    for _ in range(2):  # Second audition must reuse every cached segment.
        audition = service.start_preview(context, project_id=project_id, chapter_id=chapter_id,
                                          span_id=span_id, model_revision="test-model",
                                          voice_profile_id="voice-cloning:candidate")
        assert run_preview_once(database, blobs, context, worker_id="full-span-preview")
        audio = service.read_preview(context, project_id=project_id, job_id=audition["job_id"])
        with wave.open(io.BytesIO(audio), "rb") as reader:
            assert reader.getnframes() == 160 * len(expected_texts)
    assert [request["text"] for request in calls] == expected_texts
    assert all(request["speaker"] == "voice-cloning:candidate" for request in calls)
    narrator = next(item for item in service.get_project(context, project_id)["speakers"]
                    if item["id"] == narrator_id)
    assert narrator["casting"]["voice_profile_id"] == "voice-cloning:saved"
