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
from app.audiobook.extraction import EXTRACTOR_VERSION
from app.audiobook.spans import DETECTOR_VERSION
from app.audiobook.review_repository import PostgresAudiobookReviewRepository
from app.audiobook.annotation import DiscoveredSpeaker, proposed_speaker_id
from app.audiobook.analysis_repository import PostgresAudiobookAnalysisRepository
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


def test_deleted_project_is_hidden_and_cancels_queued_work(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-delete-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path)
        service = AudiobookService(database, blobs)
        project_id = service.create_project(context, title="Delete Test")["id"]
        submission = service.submit_source(
            context, project_id=project_id, source_format="txt",
            content=b"Chapter 1\nA source worth preserving.", filename="source.txt",
        )
        assert run_ingest_once(database, blobs, context, worker_id="test:delete-ingest")
        assert run_analyze_once(database, context, worker_id="test:delete-analyze")
        chapter_id = service.get_project(context, project_id)["chapters"][0]["id"]
        with unit_of_work(database) as work:
            PostgresAudiobookAnalysisRepository(work.connection).register_proposed_speakers(
                context,
                project_id=project_id,
                discoveries=[DiscoveredSpeaker(
                    canonical_name="Delete Me",
                    aliases=(),
                    role="background",
                    traits=(),
                )],
            )
            proposed = work.connection.execute(
                """SELECT id FROM omnix_audiobook_speakers
                    WHERE workspace_id = %s AND project_id = %s
                      AND canonical_name = 'Delete Me' AND status = 'proposed'""",
                (context.workspace_id, project_id),
            ).fetchone()
            work.commit()
        assert proposed is not None
        with service.open_source(context, project_id=project_id)[0] as source:
            assert source.read() == b"Chapter 1\nA source worth preserving."
        with unit_of_work(database) as work:
            pending = work.jobs.create_job(context, {
                "id": f"ab:job:delete:{project_id}", "module": "audiobook",
                "job_type": "audiobook.preview-span", "resource_class": "gpu:tts:preview",
                "input_payload": {"project_id": project_id},
            })
            work.connection.execute(
                """UPDATE omnix_jobs
                      SET status = 'paused',
                          metadata = metadata || '{"paused":true}'::jsonb
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, pending["id"]),
            )
            work.commit()

        service.delete_project(context, project_id=project_id)
        assert all(item["id"] != project_id for item in service.list_projects(context))
        with unit_of_work(database) as work:
            assert work.jobs.get_job(context, pending["id"])["status"] == "canceled"
            assert work.connection.execute(
                "SELECT count(*) FROM omnix_audiobook_source_revisions WHERE workspace_id = %s AND project_id = %s",
                (context.workspace_id, project_id),
            ).fetchone()[0] == 1
            work.rollback()
        for read in (
            lambda: service.get_project(context, project_id),
            lambda: service.get_chapter(context, project_id=project_id, chapter_id=chapter_id),
            lambda: service.open_source(context, project_id=project_id),
            lambda: service.list_exports(context, project_id),
            lambda: service.add_speaker(context, project_id=project_id, canonical_name="New Speaker"),
            lambda: service.reject_speaker(
                context, project_id=project_id, speaker_id=str(proposed[0]),
            ),
            lambda: service.retry_pipeline_job(context, project_id=project_id, job_id=submission["job_id"]),
            lambda: service.delete_project(context, project_id=project_id),
        ):
            with pytest.raises(KeyError):
                read()
    finally:
        database.close()


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


def test_analysis_resumes_prepared_chapters_before_publishing_review(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-analysis-resume-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path)
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Analysis Resume")
        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=b'Chapter 1\n"A voice," she said.\nChapter 2\nThe lantern glowed.',
            filename="resume.txt",
        )
        assert run_ingest_once(database, blobs, context, worker_id="test:resume-ingest")
        partial = service.get_project(context, project["id"])
        with unit_of_work(database) as work:
            PostgresAudiobookAnalysisRepository(work.connection).prepare_review(
                context, project_id=project["id"],
                source_revision_id=partial["current_source_revision_id"],
                chapter_id=partial["chapters"][0]["id"], finalize=False,
            )
            work.commit()
        assert service.get_project(context, project["id"])["review_issues"] == []
        hidden = service.get_chapter(
            context, project_id=project["id"], chapter_id=partial["chapters"][0]["id"],
        )
        assert all(span["annotation"] is None for span in hidden["spans"])
        assert run_analyze_once(database, context, worker_id="test:resume-analysis")
        completed = service.get_project(context, project["id"])
        assert completed["state"] == "review_required"
        assert completed["review_issues"]
        assert len(completed["chapters"]) == 2
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
        proposed_nita = next(speaker for speaker in detail["speakers"]
                             if speaker["canonical_name"] == "Nita")
        assert proposed_nita["status"] == "proposed"
        assert proposed_nita["occurrence_count"] >= 1
        assert any("spans" in call and "span_ids" in call for call in calls)
        assert any("source_text" in call and "span_id" in call for call in calls)
        nita = service.add_speaker(context, project_id=project["id"], canonical_name="Nita")
        assert nita["id"] == proposed_nita["id"]
        assert nita["promoted"] is True
        assert nita["reconciled_spans"] >= 1
        service.confirm_alias(context, project_id=project["id"], speaker_id=nita["id"], alias="Nita Sr.")
        assert "Nita Sr." in next(item for item in service.get_project(context, project["id"])["speakers"]
                                  if item["id"] == nita["id"])["aliases"]
        with pytest.raises(ValueError, match="another active speaker"):
            service.confirm_alias(context, project_id=project["id"], speaker_id=detail["speakers"][0]["id"],
                                  alias="Nita")
    finally:
        database.close()


def test_cross_chapter_roster_refresh_uses_persisted_alias_identity(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-roster-refresh-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Roster refresh")
        nita = service.add_speaker(
            context, project_id=project["id"], canonical_name="Nita",
        )
        service.confirm_alias(
            context, project_id=project["id"],
            speaker_id=nita["id"], alias="Ms. Nita",
        )
        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=(
                'Chapter 1\n"First line."\n'
                'Chapter 2\n"Second line."\n'
            ).encode(),
            filename="roster.txt",
        )
        assert run_ingest_once(
            database, blobs, context, worker_id="test:roster-refresh-ingest"
        )

        primary_rosters = []

        def classifier_factory():
            def classify(payload):
                if payload["task"] == "analyze_story_dialogue_full_context":
                    primary_rosters.append(payload["speaker_roster"])
                    return {
                        "characters": (
                            [{
                                "name": "Ms. Nita",
                                "aliases": [],
                                "role": "supporting",
                                "traits": [],
                            }]
                            if len(primary_rosters) == 1 else []
                        ),
                        "spans": [{
                            "span_id": span_id,
                            "speaker": "Ms. Nita",
                            "confidence": 0.99,
                            "ambiguity": None,
                        } for span_id in payload["span_ids"]],
                    }
                raise AssertionError(f"unexpected classifier task {payload['task']}")

            return classify, {
                "mode": "test-roster-refresh",
                "version": "1",
                "provider_id": "test",
                "model": "test-model",
            }

        monkeypatch.setattr("app.audiobook.worker.local_classifier", classifier_factory)
        monkeypatch.setattr(
            "app.audiobook.annotation._audit_selected", lambda _span_id: False,
        )
        assert run_analyze_once(
            database, context, worker_id="test:roster-refresh-analyze"
        )

        assert len(primary_rosters) == 2
        second = primary_rosters[1]
        active_nita = next(item for item in second if item["id"] == nita["id"])
        assert active_nita["name"] == "Nita"
        assert active_nita["status"] == "active"
        assert active_nita["aliases"] == ["Ms. Nita"]
        assert not any(
            item["name"] == "Ms. Nita" and item["status"] == "proposed"
            for item in second
        )
        with unit_of_work(database) as work:
            duplicates = work.connection.execute(
                """SELECT count(*)
                     FROM omnix_audiobook_speakers
                    WHERE workspace_id = %s AND project_id = %s
                      AND canonical_name = 'Ms. Nita'
                      AND status IN ('active', 'proposed')""",
                (context.workspace_id, project["id"]),
            ).fetchone()[0]
            work.rollback()
        assert duplicates == 0
    finally:
        database.close()


def test_identical_source_retries_style_discovery_after_provider_failure(
    tmp_path, monkeypatch,
) -> None:
    factory_calls = 0

    def classifier_factory():
        nonlocal factory_calls
        factory_calls += 1

        def classify(payload):
            if factory_calls == 1:
                raise RuntimeError("injected style discovery outage")
            assert payload["task"] == "discover_dialogue_style"
            return {
                "styles": [{
                    "id": "hyphen_dash",
                    "examples": ["- Hello there", "- Goodbye now"],
                }]
            }

        return classify, {
            "mode": "test-style-recovery",
            "version": "1",
            "provider_id": "test",
            "model": "test-model",
        }

    monkeypatch.setattr("app.audiobook.worker.local_classifier", classifier_factory)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-style-recovery-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Style recovery")
        content = (
            "Chapter 1\n"
            "- Hello there\n"
            "- Goodbye now\n"
        ).encode()

        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=content, filename="style.txt",
        )
        assert run_ingest_once(
            database, blobs, context, worker_id="test:style-recovery-first"
        )
        first = service.get_project(context, project["id"])
        first_revision = first["current_source_revision_id"]
        with unit_of_work(database) as work:
            first_metadata = work.connection.execute(
                """SELECT metadata
                     FROM omnix_audiobook_source_revisions
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, first_revision),
            ).fetchone()[0]
            work.rollback()
        assert "dialogue_style_discovery" not in dict(first_metadata or {})

        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=content, filename="style.txt",
        )
        assert run_ingest_once(
            database, blobs, context, worker_id="test:style-recovery-second"
        )
        second = service.get_project(context, project["id"])
        assert second["current_source_revision_id"] != first_revision
        with unit_of_work(database) as work:
            metadata = dict(work.connection.execute(
                """SELECT metadata
                     FROM omnix_audiobook_source_revisions
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, second["current_source_revision_id"]),
            ).fetchone()[0] or {})
            dialogue = work.connection.execute(
                """SELECT s.source_text
                     FROM omnix_audiobook_spans s
                     JOIN omnix_audiobook_chapters c
                       ON c.workspace_id = s.workspace_id AND c.id = s.chapter_id
                    WHERE c.workspace_id = %s AND c.source_revision_id = %s
                      AND s.structural_kind = 'dialogue'
                    ORDER BY c.ordinal, s.ordinal""",
                (context.workspace_id, second["current_source_revision_id"]),
            ).fetchall()
            work.connection.execute(
                """UPDATE omnix_jobs
                      SET status = 'canceled', completed_at = CURRENT_TIMESTAMP,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s AND module = 'audiobook'
                      AND job_type = 'audiobook.analyze'
                      AND input_payload->>'project_id' = %s
                      AND status IN ('queued', 'waiting', 'retrying', 'paused')""",
                (context.workspace_id, project["id"]),
            )
            work.commit()

        assert metadata["dialogue_style_discovery"]["styles"] == ["hyphen_dash"]
        assert [str(row[0]) for row in dialogue] == [
            "- Hello there\n", "- Goodbye now\n",
        ]
    finally:
        database.close()


def test_rejected_character_stays_rejected_when_classifier_rediscovers_it(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-rejected-character-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Rejected character")
        speaker_id = proposed_speaker_id(project["id"], "Ms. Nita")

        with unit_of_work(database) as work:
            work.connection.execute(
                """INSERT INTO omnix_audiobook_speakers
                    (id, workspace_id, project_id, canonical_name, display_name,
                     kind, status, analysis_metadata)
                   VALUES (%s::uuid, %s, %s, 'Ms. Nita', 'Ms. Nita',
                           'character', 'rejected', '{}'::jsonb)""",
                (speaker_id, context.workspace_id, project["id"]),
            )
            repository = PostgresAudiobookAnalysisRepository(work.connection)
            repository.register_proposed_speakers(
                context,
                project_id=project["id"],
                discoveries=[DiscoveredSpeaker(
                    canonical_name="Ms. Nita",
                    aliases=("Nita Senior",),
                    role="supporting",
                    traits=("skeptical",),
                )],
            )
            row = work.connection.execute(
                """SELECT status, analysis_metadata
                     FROM omnix_audiobook_speakers
                    WHERE workspace_id = %s AND project_id = %s
                      AND id = %s::uuid""",
                (context.workspace_id, project["id"], speaker_id),
            ).fetchone()
            aliases = work.connection.execute(
                """SELECT alias, status
                     FROM omnix_audiobook_speaker_aliases
                    WHERE workspace_id = %s AND project_id = %s
                      AND speaker_id = %s::uuid""",
                (context.workspace_id, project["id"], speaker_id),
            ).fetchall()
            work.commit()

        assert row[0] == "rejected"
        assert dict(row[1]) == {
            "role": "supporting",
            "traits": ["skeptical"],
        }
        assert aliases == []

        restored = service.add_speaker(
            context, project_id=project["id"], canonical_name="Ms. Nita",
        )
        assert restored["id"] == speaker_id
        assert restored["status"] == "active"
        assert restored["promoted"] is True
    finally:
        database.close()


def test_batch_classifier_persists_character_profile_and_proposed_alias(tmp_path, monkeypatch) -> None:
    def classifier():
        def classify(payload):
            return {
                "characters": [{
                    "name": "Nita",
                    "aliases": ["Ms. Nita"],
                    "role": "supporting",
                    "traits": ["quick-witted", "skeptical"],
                    "estimated_age": "20s",
                    "gender_presentation": "female",
                }],
                "spans": [{
                    "span_id": item["span_id"],
                    "speaker": "Ms. Nita",
                    "role": "dialogue",
                    "delivery": "dry",
                    "confidence": 0.97,
                } for item in payload["spans"]],
            }
        return classify, {"mode": "test-batch-classifier", "version": "3"}

    monkeypatch.setattr("app.audiobook.worker.local_classifier", classifier)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-profile-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Character profile")
        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=b'Chapter 1\n"Not impressed," said Nita.\n',
            filename="profile.txt",
        )
        assert run_ingest_once(database, blobs, context, worker_id="test:profile-ingest")
        assert run_analyze_once(database, context, worker_id="test:profile-analyze")

        detail = service.get_project(context, project["id"])
        nita = next(item for item in detail["speakers"]
                    if item["canonical_name"] == "Nita")
        assert nita["status"] == "proposed"
        assert nita["occurrence_count"] == 1
        assert nita["analysis_metadata"] == {
            "role": "supporting",
            "traits": ["quick-witted", "skeptical"],
            "estimated_age": "20s",
            "gender_presentation": "female",
        }
        assert nita["aliases"] == []
        assert nita["proposed_aliases"] == ["Ms. Nita"]
        with pytest.raises(ValueError, match="reassign or resolve"):
            service.reject_speaker(
                context, project_id=project["id"], speaker_id=nita["id"],
            )

        with unit_of_work(database) as work:
            alias = work.connection.execute(
                """SELECT alias, status
                     FROM omnix_audiobook_speaker_aliases
                    WHERE workspace_id = %s AND project_id = %s
                      AND speaker_id = %s::uuid""",
                (context.workspace_id, project["id"], nita["id"]),
            ).fetchone()
            work.rollback()
        assert alias == ("Ms. Nita", "proposed")

        with pytest.raises(ValueError, match="canonical name"):
            service.confirm_alias(
                context, project_id=project["id"],
                speaker_id=nita["id"], alias="Nita",
            )

        confirmed_alias = service.confirm_alias(
            context, project_id=project["id"],
            speaker_id=nita["id"], alias="Ms. Nita",
        )
        assert confirmed_alias["alias"] == "Ms. Nita"
        refreshed = service.get_project(context, project["id"])
        refreshed_nita = next(
            item for item in refreshed["speakers"]
            if item["canonical_name"] == "Nita"
        )
        assert refreshed_nita["aliases"] == ["Ms. Nita"]
        assert refreshed_nita["proposed_aliases"] == []
        with unit_of_work(database) as work:
            alias_rows = work.connection.execute(
                """SELECT alias, status
                     FROM omnix_audiobook_speaker_aliases
                    WHERE workspace_id = %s AND project_id = %s
                      AND lower(alias) = lower(%s)
                    ORDER BY status""",
                (context.workspace_id, project["id"], "Ms. Nita"),
            ).fetchall()
            work.rollback()
        assert alias_rows == [("Ms. Nita", "confirmed")]
        with pytest.raises(
            ValueError, match="confirmed alias of another speaker"
        ):
            service.add_speaker(
                context, project_id=project["id"], canonical_name="Ms. Nita",
            )

        # A rejected duplicate from an earlier classifier pass must not shadow
        # the now-confirmed alias authority.
        rejected_alias_id = proposed_speaker_id(project["id"], "Ms. Nita")
        with unit_of_work(database) as work:
            work.connection.execute(
                """INSERT INTO omnix_audiobook_speakers
                    (id, workspace_id, project_id, canonical_name, display_name,
                     kind, status, analysis_metadata)
                   VALUES (%s::uuid, %s, %s, 'Ms. Nita', 'Ms. Nita',
                           'character', 'rejected', '{}'::jsonb)
                   ON CONFLICT (id) DO UPDATE
                     SET status = 'rejected', analysis_metadata = '{}'::jsonb""",
                (rejected_alias_id, context.workspace_id, project["id"]),
            )
            work.commit()

        # Rediscovering the character by a confirmed alias must enrich the
        # existing active identity rather than create a duplicate proposal.
        with unit_of_work(database) as work:
            repository = PostgresAudiobookAnalysisRepository(work.connection)
            repository.register_proposed_speakers(
                context,
                project_id=project["id"],
                discoveries=[DiscoveredSpeaker(
                    canonical_name="Ms. Nita",
                    aliases=("Nita",),
                    role="lead",
                    traits=("resilient",),
                )],
            )
            duplicate = work.connection.execute(
                """SELECT count(*)
                     FROM omnix_audiobook_speakers
                    WHERE workspace_id = %s AND project_id = %s
                      AND canonical_name = 'Ms. Nita'
                      AND status IN ('active', 'proposed')""",
                (context.workspace_id, project["id"]),
            ).fetchone()[0]
            enriched = work.connection.execute(
                """SELECT analysis_metadata
                     FROM omnix_audiobook_speakers
                    WHERE workspace_id = %s AND project_id = %s
                      AND id = %s::uuid""",
                (context.workspace_id, project["id"], nita["id"]),
            ).fetchone()[0]
            rejected_tombstone = work.connection.execute(
                """SELECT status, analysis_metadata
                     FROM omnix_audiobook_speakers
                    WHERE workspace_id = %s AND project_id = %s
                      AND id = %s::uuid""",
                (context.workspace_id, project["id"], rejected_alias_id),
            ).fetchone()
            work.commit()
        assert duplicate == 0
        assert rejected_tombstone[0] == "rejected"
        assert dict(rejected_tombstone[1]) == {}
        assert dict(enriched)["role"] == "lead"
        assert dict(enriched)["traits"] == ["resilient"]
        refreshed_after_rediscovery = service.get_project(context, project["id"])
        rediscovered_nita = next(
            item for item in refreshed_after_rediscovery["speakers"]
            if item["id"] == nita["id"]
        )
        assert rediscovered_nita["aliases"] == ["Ms. Nita"]
        assert rediscovered_nita["proposed_aliases"] == []

        with unit_of_work(database) as work:
            repository = PostgresAudiobookAnalysisRepository(work.connection)
            repository.register_proposed_speakers(
                context,
                project_id=project["id"],
                discoveries=[DiscoveredSpeaker(
                    canonical_name="Unused Detection",
                    aliases=("Unused Alias",),
                    role="background",
                    traits=(),
                )],
            )
            unused = work.connection.execute(
                """SELECT id FROM omnix_audiobook_speakers
                    WHERE workspace_id = %s AND project_id = %s
                      AND canonical_name = 'Unused Detection'
                      AND status = 'proposed'""",
                (context.workspace_id, project["id"]),
            ).fetchone()
            work.commit()
        confirmed_unused_alias = service.confirm_alias(
            context, project_id=project["id"],
            speaker_id=str(unused[0]), alias="Unused Alias",
        )
        assert confirmed_unused_alias["alias"] == "Unused Alias"

        rejected = service.reject_speaker(
            context, project_id=project["id"], speaker_id=str(unused[0]),
        )
        assert rejected["status"] == "rejected"
        assert all(
            item["canonical_name"] != "Unused Detection"
            for item in service.get_project(context, project["id"])["speakers"]
        )
        with unit_of_work(database) as work:
            rejected_alias = work.connection.execute(
                """SELECT status
                     FROM omnix_audiobook_speaker_aliases
                    WHERE workspace_id = %s AND project_id = %s
                      AND speaker_id = %s::uuid AND alias = %s""",
                (
                    context.workspace_id, project["id"],
                    str(unused[0]), "Unused Alias",
                ),
            ).fetchone()
            work.rollback()
        assert rejected_alias == ("rejected",)

        assert detail["review_issues"] == []
        chapter = service.get_chapter(
            context, project_id=project["id"], chapter_id=detail["chapters"][0]["id"],
        )
        dialogue = next(
            item for item in chapter["spans"]
            if item["structural_kind"] == "dialogue"
        )
        assert dialogue["annotation"]["speaker_id"] == nita["id"]

        with unit_of_work(database) as work:
            casting = PostgresAudiobookReviewRepository(work.connection).assign_voice(
                context, project_id=project["id"], speaker_id=nita["id"],
                voice_profile_id="voice-cloning:test-detected",
                voice_revision_hash="a" * 64,
            )
            status = work.connection.execute(
                """SELECT status FROM omnix_audiobook_speakers
                    WHERE workspace_id = %s AND project_id = %s
                      AND id = %s::uuid""",
                (context.workspace_id, project["id"], nita["id"]),
            ).fetchone()[0]
            work.commit()
        assert casting["speaker_id"] == nita["id"]
        assert status == "active"
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
        assert sum(len(chapter["spans"]) for chapter in detail["chapters"]) > 0
        assert all(
            "".join(span["source_text"] for span in chapter["spans"])
            == chapter["canonical_text"]
            for chapter in detail["chapters"]
        )
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
    if sys.argv[5] == "before":
        os._exit(136)
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
        before = subprocess.run(
            [sys.executable, "-c", child_code, os.environ["OMNIX_TEST_DATABASE_URL"],
             str(blobs.root), str(reference), encoded, "before"],
            env=child_env, capture_output=True, text=True, timeout=40,
        )
        assert before.returncode == 136, before.stderr
        with unit_of_work(database) as work:
            first_attempt = work.connection.execute(
                """SELECT j.id, COALESCE(jsonb_array_length(b.completed_keys), 0)
                     FROM omnix_jobs j
                     LEFT JOIN omnix_audiobook_render_batches b ON b.job_id = j.id
                    WHERE j.workspace_id = %s AND j.status = 'running'
                      AND j.input_payload->>'project_id' = %s""",
                (context.workspace_id, project["id"]),
            ).fetchone()
            assert first_attempt and first_attempt[1] == 0
            work.connection.execute(
                """UPDATE omnix_jobs SET lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, first_attempt[0]),
            )
            work.commit()
        crashed = subprocess.run(
            [sys.executable, "-c", child_code, os.environ["OMNIX_TEST_DATABASE_URL"],
             str(blobs.root), str(reference), encoded, "after"],
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
        with unit_of_work(database) as work:
            total_units = sum(
                len(load_chapter_units(work.connection, context,
                                       project_id=project["id"], chapter_id=chapter["id"]))
                for chapter in detail["chapters"]
            )
            rendered_count = work.connection.execute(
                """SELECT count(*) FROM omnix_audiobook_renders r
                     JOIN omnix_audiobook_spans s ON s.id = r.span_id
                     JOIN omnix_audiobook_chapters c ON c.id = s.chapter_id
                    WHERE c.source_revision_id = %s""",
                (detail["current_source_revision_id"],),
            ).fetchone()[0]
            diagnostics = work.connection.execute(
                """SELECT diagnostics FROM omnix_audiobook_renders r
                     JOIN omnix_audiobook_spans s ON s.id = r.span_id AND s.workspace_id = r.workspace_id
                     JOIN omnix_audiobook_chapters c ON c.id = s.chapter_id AND c.workspace_id = s.workspace_id
                    WHERE r.workspace_id = %s AND c.source_revision_id = %s LIMIT 1""",
                (context.workspace_id, detail["current_source_revision_id"]),
            ).fetchone()[0]
            work.rollback()
        assert rendered_count == total_units
        assert provider.calls == total_units - 1
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
            assert len(report["render_details"]) == total_units
            assert report["generation_summary"]["render_count"] == total_units
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
        progress = service.get_project(context, project["id"])["render_jobs"][0]["progress"]
        assert progress["generated"] == provider.calls
        assert progress["cache_hits"] == 0
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
        service.set_audiobook_mode(
            context, project_id=project["id"], mode="standard"
        )
        content = b'Chapter 1\n"Hello," said Nita. More words.\nChapter 2\nThe next chapter begins.'
        service.submit_source(context, project_id=project["id"], source_format="txt",
                              content=content, filename="render.txt")
        assert run_ingest_once(database, blobs, context, worker_id="test:ingest")
        assert run_analyze_once(database, context, worker_id="test:analyze")
        detail = service.get_project(context, project["id"])
        narrator = detail["speakers"][0]["id"]
        nita = service.add_speaker(context, project_id=project["id"], canonical_name="Nita")["id"]
        for issue in service.get_project(context, project["id"])["review_issues"]:
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
        assert service.cancel_job(context, project_id=project["id"],
                                  job_id=audition["job_id"])["cancellation_requested"]
        with pytest.raises(KeyError):
            service.cancel_job(context, project_id="another-project", job_id=audition["job_id"])
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
            with unit_of_work(database) as work:
                completed_chapters = work.connection.execute(
                    """SELECT count(*) FROM omnix_jobs WHERE workspace_id = %s
                         AND job_type = 'audiobook.render-chapter'
                         AND input_payload->>'render_run_id' = %s
                         AND status = 'completed'""",
                    (context.workspace_id, submission["render_run_id"]),
                ).fetchone()[0]
                if completed_chapters == 1:
                    queued_assemblies = work.connection.execute(
                        """SELECT count(*) FROM omnix_jobs WHERE workspace_id = %s
                             AND job_type = 'audiobook.assemble-chapter'
                             AND input_payload->>'render_run_id' = %s""",
                        (context.workspace_id, submission["render_run_id"]),
                    ).fetchone()[0]
                    assert queued_assemblies == 1
                work.rollback()
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
                input_path = Path(command[command.index("-i") + 1])
                if "concat" not in command:
                    Path(command[-1]).write_bytes(input_path.read_bytes())
                    return
                chapter_paths = [
                    input_path.parent / line.removeprefix("file ")
                    for line in input_path.read_text(encoding="utf-8").splitlines()
                    if line.startswith("file ")
                ]
                with wave.open(str(Path(command[-1])), "wb") as output:
                    for index, chapter_path in enumerate(chapter_paths):
                        with wave.open(str(chapter_path), "rb") as chapter:
                            if index == 0:
                                output.setnchannels(chapter.getnchannels())
                                output.setsampwidth(chapter.getsampwidth())
                                output.setframerate(chapter.getframerate())
                            output.writeframes(chapter.readframes(chapter.getnframes()))

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

        # A frozen export must not become durable if the project switches to a
        # different render run while the encoder is working.
        stale_submission = service.start_export(
            context, project_id=project["id"], format="wav"
        )
        with unit_of_work(database) as work:
            original_render_run_id = work.connection.execute(
                """SELECT settings->>'current_render_run_id'
                     FROM omnix_audiobook_projects
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, project["id"]),
            ).fetchone()[0]
            work.connection.execute(
                """UPDATE omnix_audiobook_projects
                      SET settings = jsonb_set(
                          settings, '{current_render_run_id}',
                          to_jsonb(%s::text), true
                      )
                    WHERE workspace_id = %s AND id = %s""",
                ("ab:run:replacement", context.workspace_id, project["id"]),
            )
            work.commit()
        assert run_export_once(
            database, blobs, context, worker_id="test:stale-export"
        )
        assert len(service.list_exports(context, project["id"])) == 1
        with unit_of_work(database) as work:
            stale_job = work.jobs.get_job(context, stale_submission["job_id"])
            assert stale_job["status"] == "failed"
            assert (
                stale_job["error"]["message"]
                == "export manifest no longer matches the current project state"
            )
            work.connection.execute(
                """UPDATE omnix_audiobook_projects
                      SET settings = jsonb_set(
                          settings, '{current_render_run_id}',
                          to_jsonb(%s::text), true
                      )
                    WHERE workspace_id = %s AND id = %s""",
                (
                    str(original_render_run_id),
                    context.workspace_id,
                    project["id"],
                ),
            )
            work.commit()

        metadata_stale = service.start_export(
            context, project_id=project["id"], format="wav"
        )
        service.update_project(
            context,
            project_id=project["id"],
            title="Render Recovery Renamed",
            author="",
        )
        assert run_export_once(
            database, blobs, context, worker_id="test:stale-metadata-export"
        )
        assert len(service.list_exports(context, project["id"])) == 1
        with unit_of_work(database) as work:
            metadata_job = work.jobs.get_job(
                context, metadata_stale["job_id"]
            )
            work.rollback()
        assert metadata_job["status"] == "failed"
        assert (
            metadata_job["error"]["message"]
            == "export manifest no longer matches the current project state"
        )
        service.update_project(
            context,
            project_id=project["id"],
            title="Render Recovery",
            author="",
        )

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



def test_identical_source_resubmit_reuses_empty_style_discovery(
    tmp_path, monkeypatch,
) -> None:
    style_calls = 0

    def classifier():
        def classify(payload):
            nonlocal style_calls
            assert payload["task"] == "discover_dialogue_style"
            style_calls += 1
            return {"styles": []}
        return classify, {
            "mode": "test-empty-style-classifier",
            "provider_id": "test",
            "model": "test-style-model",
        }

    monkeypatch.setattr("app.audiobook.worker.local_classifier", classifier)
    monkeypatch.setattr(
        "app.audiobook.worker.local_structure_classifier", lambda: None
    )
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000,
        application_name="omnix-audiobook-empty-style-resubmit-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Stable no-style source")
        content = ("Chapter 1\n" + ("Narration only. " * 140)).encode()

        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=content, filename="plain.txt",
        )
        assert run_ingest_once(
            database, blobs, context, worker_id="test:empty-style-first"
        )
        first_revision = service.get_project(
            context, project["id"]
        )["current_source_revision_id"]
        assert style_calls == 1

        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=content, filename="plain-again.txt",
        )
        assert run_ingest_once(
            database, blobs, context, worker_id="test:empty-style-second"
        )
        detail = service.get_project(context, project["id"])
        assert detail["current_source_revision_id"] == first_revision
        assert style_calls == 1

        with unit_of_work(database) as work:
            rows = work.connection.execute(
                """SELECT metadata->'dialogue_style_discovery'->'styles'
                     FROM omnix_audiobook_source_revisions
                    WHERE workspace_id = %s AND project_id = %s""",
                (context.workspace_id, project["id"]),
            ).fetchall()
            work.connection.execute(
                """UPDATE omnix_jobs
                      SET status = 'canceled', completed_at = CURRENT_TIMESTAMP,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s AND module = 'audiobook'
                      AND job_type = 'audiobook.analyze'
                      AND input_payload->>'project_id' = %s
                      AND status IN ('queued', 'waiting', 'retrying')""",
                (context.workspace_id, project["id"]),
            )
            work.commit()
        assert len(rows) == 1
        assert list(rows[0][0]) == []
    finally:
        database.close()


def test_identical_source_resubmit_reuses_discovered_dialogue_segmentation(
    tmp_path, monkeypatch,
) -> None:
    style_calls = 0

    def classifier():
        def classify(payload):
            nonlocal style_calls
            assert payload["task"] == "discover_dialogue_style"
            style_calls += 1
            if style_calls == 1:
                return {
                    "styles": [{
                        "id": "low_double_quotes",
                        "examples": ["„Hallo,“"],
                    }]
                }
            return {"styles": []}
        return classify, {
            "mode": "test-style-classifier",
            "provider_id": "test",
            "model": "test-style-model",
        }

    monkeypatch.setattr("app.audiobook.worker.local_classifier", classifier)
    monkeypatch.setattr(
        "app.audiobook.worker.local_structure_classifier", lambda: None
    )
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000,
        application_name="omnix-audiobook-style-resubmit-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Stable style source")
        content = (
            "Chapter 1\n"
            "„Hallo,“ sagte Nita.\n"
            "The narrator continues.\n"
        ).encode()

        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=content, filename="styled.txt",
        )
        assert run_ingest_once(
            database, blobs, context, worker_id="test:style-first-ingest"
        )
        first_revision = service.get_project(
            context, project["id"]
        )["current_source_revision_id"]
        assert first_revision
        assert style_calls == 1

        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=content, filename="styled-again.txt",
        )
        assert run_ingest_once(
            database, blobs, context, worker_id="test:style-second-ingest"
        )
        # This test covers ingest identity only. Do not leak its queued analysis
        # job into the shared PostgreSQL integration workspace, where a later
        # run_analyze_once() could otherwise claim the wrong project's work.
        with unit_of_work(database) as work:
            work.connection.execute(
                """UPDATE omnix_jobs
                      SET status = 'canceled', completed_at = CURRENT_TIMESTAMP,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s AND module = 'audiobook'
                      AND job_type = 'audiobook.analyze'
                      AND input_payload->>'project_id' = %s
                      AND status IN ('queued', 'waiting', 'retrying')""",
                (context.workspace_id, project["id"]),
            )
            work.commit()
        detail = service.get_project(context, project["id"])
        assert detail["current_source_revision_id"] == first_revision
        assert style_calls == 1

        with unit_of_work(database) as work:
            revision_count = int(work.connection.execute(
                """SELECT count(*) FROM omnix_audiobook_source_revisions
                    WHERE workspace_id = %s AND project_id = %s""",
                (context.workspace_id, project["id"]),
            ).fetchone()[0])
            styles = work.connection.execute(
                """SELECT metadata->'dialogue_style_discovery'->'styles'
                     FROM omnix_audiobook_source_revisions
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, first_revision),
            ).fetchone()[0]
            work.rollback()
        assert revision_count == 1
        assert list(styles) == ["low_double_quotes"]
    finally:
        database.close()


def test_identical_source_resubmit_reuses_revision_and_recovers_terminal_analysis(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-resubmit-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Idempotent source")
        content = b"Chapter 1\nThis exact source must remain stable."

        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=content, filename="same.txt",
        )
        assert run_ingest_once(database, blobs, context, worker_id="test:first-ingest")
        first_revision = service.get_project(context, project["id"])["current_source_revision_id"]
        assert first_revision

        with unit_of_work(database) as work:
            original_analysis = work.connection.execute(
                """SELECT id FROM omnix_jobs
                    WHERE workspace_id = %s AND module = 'audiobook'
                      AND job_type = 'audiobook.analyze'
                      AND input_payload->>'project_id' = %s
                    ORDER BY created_at DESC LIMIT 1""",
                (context.workspace_id, project["id"]),
            ).fetchone()
            assert original_analysis
            work.connection.execute(
                """UPDATE omnix_jobs
                      SET status = 'failed', attempt_count = max_attempts,
                          completed_at = CURRENT_TIMESTAMP,
                          error = '{"code":"injected_terminal_analysis"}'::jsonb
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, original_analysis[0]),
            )
            work.commit()

        second = service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=content, filename="same-again.txt",
        )
        assert second["source_asset_id"]
        assert run_ingest_once(database, blobs, context, worker_id="test:second-ingest")
        detail = service.get_project(context, project["id"])
        assert detail["current_source_revision_id"] == first_revision

        with unit_of_work(database) as work:
            revision_count = int(work.connection.execute(
                """SELECT count(*) FROM omnix_audiobook_source_revisions
                    WHERE workspace_id = %s AND project_id = %s""",
                (context.workspace_id, project["id"]),
            ).fetchone()[0])
            analysis_rows = work.connection.execute(
                """SELECT id, status, metadata FROM omnix_jobs
                    WHERE workspace_id = %s AND module = 'audiobook'
                      AND job_type = 'audiobook.analyze'
                      AND input_payload->>'project_id' = %s
                    ORDER BY created_at""",
                (context.workspace_id, project["id"]),
            ).fetchall()
            work.rollback()
        assert revision_count == 1
        assert len(analysis_rows) == 2
        assert analysis_rows[0][1] == "failed"
        assert dict(analysis_rows[0][2]).get("superseded_by") == str(analysis_rows[1][0])
        assert analysis_rows[1][1] == "queued"
        assert dict(analysis_rows[1][2]).get("retry_of") == str(analysis_rows[0][0])

        assert run_analyze_once(database, context, worker_id="test:recovered-analysis")
        assert service.get_project(context, project["id"])["state"] == "ready_to_render"
    finally:
        database.close()



def test_reclassify_rediscover_styles_after_initial_classifier_outage(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    monkeypatch.setattr(
        "app.audiobook.worker.local_structure_classifier", lambda: None
    )
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000,
        application_name="omnix-audiobook-style-rediscovery-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Style rediscovery")
        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=(
                "Chapter 1\n"
                "„Hallo,“ sagte Nita.\n"
                "The narrator continues.\n"
            ).encode(),
            filename="style-rediscovery.txt",
        )
        assert run_ingest_once(
            database, blobs, context, worker_id="test:style-rediscovery-ingest"
        )
        assert run_analyze_once(
            database, context, worker_id="test:style-rediscovery-analysis"
        )
        before = service.get_project(context, project["id"])
        assert any(
            issue["reason"] == "POSSIBLE_MISSED_DIALOGUE"
            for issue in before["review_issues"]
        )

        with unit_of_work(database) as work:
            paused_id = f"ab:test:paused-analysis:{project['id']}"
            work.jobs.create_job(context, {
                "id": paused_id,
                "module": "audiobook",
                "job_type": "audiobook.analyze",
                "resource_class": "cpu",
                "input_payload": {
                    "project_id": project["id"],
                    "source_revision_id": before["current_source_revision_id"],
                },
            })
            work.connection.execute(
                """UPDATE omnix_jobs
                      SET status = 'paused',
                          metadata = metadata || '{"paused":true}'::jsonb
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, paused_id),
            )
            work.commit()
        with pytest.raises(ValueError, match="classification is already running"):
            service.reclassify_source(context, project_id=project["id"])
        with unit_of_work(database) as work:
            work.jobs.request_cancel(context, paused_id)
            work.commit()

        queued = service.reclassify_source(
            context, project_id=project["id"]
        )
        with unit_of_work(database) as work:
            row = work.connection.execute(
                """SELECT job_type, input_payload, metadata
                     FROM omnix_jobs
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, queued["job_id"]),
            ).fetchone()
            assert row[0] == "audiobook.ingest"
            assert bool(dict(row[1]).get("force_reclassify")) is True
            assert (
                dict(row[2]).get("migration", {}).get(
                    "dialogue_style_rediscovery"
                )
                is True
            )
            work.connection.execute(
                """UPDATE omnix_jobs
                      SET status = 'canceled', completed_at = CURRENT_TIMESTAMP,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, queued["job_id"]),
            )
            work.commit()
    finally:
        database.close()


def test_reclassify_migrates_stale_span_detector_before_ai_analysis(
    tmp_path, monkeypatch,
) -> None:
    def classifier():
        def classify(payload):
            return {
                "characters": [{"name": "Nita", "aliases": []}],
                "spans": [{
                    "span_id": item["span_id"],
                    "speaker": "Nita",
                    "role": "dialogue",
                    "delivery": "",
                    "confidence": 0.99,
                } for item in payload["spans"]],
            }
        return classify, {
            "mode": "test-full-story-classifier",
            "version": "audiobook-classifier-v5",
            "reasoning_effort": "xhigh",
        }

    monkeypatch.setattr("app.audiobook.worker.local_classifier", classifier)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-reextract-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Stale span migration")
        source = b'Chapter 1\n"Hello," said Nita.\n'
        # Build the first durable revision exactly as an older runtime would:
        # old extractor/detector versions participate in that revision identity.
        monkeypatch.setattr(
            "app.audiobook.extraction.EXTRACTOR_VERSION",
            "audiobook-extractor-v6",
        )
        monkeypatch.setattr(
            "app.audiobook.extraction.UnicodeDialogueDetector.version",
            "audiobook-spans-v3",
        )
        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=source, filename="stale.txt",
        )
        assert run_ingest_once(
            database, blobs, context, worker_id="test:stale-span-ingest",
        )
        assert run_analyze_once(
            database, context, worker_id="test:stale-span-analysis",
        )
        before = service.get_project(context, project["id"])
        old_revision = before["current_source_revision_id"]

        # Simulate restarting onto the current code before the user clicks
        # Reclassify. AudiobookService imported the current v7/v4 migration
        # targets when this test module loaded.
        monkeypatch.setattr(
            "app.audiobook.extraction.EXTRACTOR_VERSION",
            EXTRACTOR_VERSION,
        )
        monkeypatch.setattr(
            "app.audiobook.extraction.UnicodeDialogueDetector.version",
            DETECTOR_VERSION,
        )

        queued = service.reclassify_source(
            context, project_id=project["id"],
        )
        with unit_of_work(database) as work:
            ingest = work.connection.execute(
                """SELECT job_type, input_payload
                     FROM omnix_jobs
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, queued["job_id"]),
            ).fetchone()
            work.rollback()
        assert ingest[0] == "audiobook.ingest"
        assert bool(dict(ingest[1]).get("force_reclassify")) is True

        assert run_ingest_once(
            database, blobs, context, worker_id="test:stale-span-reextract",
        )
        migrated = service.get_project(context, project["id"])
        new_revision = migrated["current_source_revision_id"]
        assert new_revision != old_revision

        with unit_of_work(database) as work:
            versions = work.connection.execute(
                """SELECT DISTINCT r.extractor_version, s.detector_version
                     FROM omnix_audiobook_source_revisions r
                     JOIN omnix_audiobook_chapters c
                       ON c.workspace_id = r.workspace_id
                      AND c.source_revision_id = r.id
                     JOIN omnix_audiobook_spans s
                       ON s.workspace_id = c.workspace_id
                      AND s.chapter_id = c.id
                    WHERE r.workspace_id = %s AND r.id = %s""",
                (context.workspace_id, new_revision),
            ).fetchall()
            analysis = work.connection.execute(
                """SELECT input_payload
                     FROM omnix_jobs
                    WHERE workspace_id = %s
                      AND module = 'audiobook'
                      AND job_type = 'audiobook.analyze'
                      AND input_payload->>'source_revision_id' = %s
                    ORDER BY created_at DESC LIMIT 1""",
                (context.workspace_id, new_revision),
            ).fetchone()
            work.rollback()
        assert versions == [(EXTRACTOR_VERSION, DETECTOR_VERSION)]
        assert bool(dict(analysis[0]).get("force_reclassify")) is True

        assert run_analyze_once(
            database, context, worker_id="test:stale-span-reanalyze",
        )
        assert service.get_project(context, project["id"])["state"] == "ready_to_render"
    finally:
        database.close()


def test_confirmed_alias_reconciles_matching_unresolved_annotation_only(tmp_path, monkeypatch) -> None:
    def classifier():
        def classify(payload):
            source = str(payload["source_text"])
            return {
                "span_id": payload["span_id"],
                "speaker": "Nita Sr." if '"' in source else "Narrator",
                "role": "dialogue" if '"' in source else "narration",
                "delivery": "quiet" if '"' in source else "",
            }
        return classify, {"mode": "test-classifier", "version": "1"}

    monkeypatch.setattr("app.audiobook.worker.local_classifier", classifier)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-alias-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Alias reconciliation")
        source = b'Chapter 1\n"Nita speaks."\nThe narrator continues.'
        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=source, filename="alias.txt",
        )
        assert run_ingest_once(database, blobs, context, worker_id="test:alias-ingest")
        assert run_analyze_once(database, context, worker_id="test:alias-analyze")
        before = service.get_project(context, project["id"])
        issue = next(item for item in before["review_issues"]
                     if item.get("speaker_candidate") == "Nita Sr.")
        proposed_alias_candidate = next(
            item for item in before["speakers"]
            if item["canonical_name"] == "Nita Sr."
        )
        source_before = issue["source_text"]

        nita = service.add_speaker(
            context, project_id=project["id"], canonical_name="Nita",
        )
        result = service.confirm_alias(
            context, project_id=project["id"], speaker_id=nita["id"], alias="Nita Sr.",
        )
        assert result["reconciled_spans"] >= 1
        with pytest.raises(
            ValueError, match="confirmed alias of another speaker"
        ):
            service.add_speaker(
                context, project_id=project["id"], canonical_name="Nita Sr.",
            )
        with pytest.raises(
            ValueError, match="speaker is not available for alias confirmation"
        ):
            service.confirm_alias(
                context,
                project_id=project["id"],
                speaker_id=proposed_alias_candidate["id"],
                alias="Nita Junior",
            )

        after = service.get_project(context, project["id"])
        assert all(item["id"] != issue["id"] for item in after["review_issues"])
        chapter = service.get_chapter(
            context, project_id=project["id"], chapter_id=issue["chapter_id"],
        )
        revised = next(item for item in chapter["spans"] if item["id"] == issue["span_id"])
        assert revised["source_text"] == source_before
        assert revised["annotation"]["speaker_id"] == nita["id"]
        assert revised["annotation"]["review_status"] == "user_resolved"
        assert revised["annotation"]["revision"] >= 2
    finally:
        database.close()


def test_terminal_assembly_retry_can_finish_mastering(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-assembly-retry-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Assembly recovery")
        service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=b"Chapter 1\nOnly narration is needed for this recovery test.",
            filename="assembly.txt",
        )
        assert run_ingest_once(database, blobs, context, worker_id="test:assembly-ingest")
        assert run_analyze_once(database, context, worker_id="test:assembly-analyze")
        detail = service.get_project(context, project["id"])
        assert detail["state"] == "ready_to_render"
        narrator = next(item for item in detail["speakers"] if item["kind"] == "narrator")

        reference = tmp_path / "narrator.wav"
        reference.write_bytes(b"assembly retry narrator")
        with unit_of_work(database) as work:
            PostgresAudiobookReviewRepository(work.connection).assign_voice(
                context, project_id=project["id"], speaker_id=narrator["id"],
                voice_profile_id="voice-cloning:assembly-retry",
                voice_revision_hash=bytes_hash(reference.read_bytes()),
            )
            work.commit()
        profile = SimpleNamespace(
            id="voice-cloning:assembly-retry", storage_path=str(reference), metadata={},
        )
        monkeypatch.setattr(
            "app.audiobook.render_service.discover_canonical_voice_clone_assets",
            lambda: [profile],
        )

        audio_buffer = io.BytesIO()
        with wave.open(audio_buffer, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16000)
            writer.writeframes(b"\xe8\x03\x18\xfc" * 400)
        encoded = base64.b64encode(audio_buffer.getvalue()).decode()

        class Provider:
            def generate_audio_batch(self, requests):
                return [{"success": True, "audio": encoded} for _ in requests]

        monkeypatch.setattr("app.audiobook.render_service.get_tts_provider",
                            lambda _name: Provider())
        service.start_render(
            context, project_id=project["id"], model_revision="assembly-retry-model",
        )
        assert run_render_once(database, blobs, context, worker_id="test:assembly-render")
        assert service.get_project(context, project["id"])["state"] == "mastering"

        with unit_of_work(database) as work:
            failed = work.connection.execute(
                """SELECT id FROM omnix_jobs
                    WHERE workspace_id = %s AND module = 'audiobook'
                      AND job_type = 'audiobook.assemble-chapter'
                      AND input_payload->>'project_id' = %s
                    ORDER BY created_at DESC LIMIT 1""",
                (context.workspace_id, project["id"]),
            ).fetchone()
            assert failed
            work.connection.execute(
                """UPDATE omnix_jobs
                      SET status = 'failed', attempt_count = max_attempts,
                          completed_at = CURRENT_TIMESTAMP,
                          error = '{"code":"injected_assembly_failure","retryable":false}'::jsonb
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, failed[0]),
            )
            work.commit()

        retry = service.retry_pipeline_job(
            context, project_id=project["id"], job_id=str(failed[0]),
        )
        assert retry["retry_of"] == str(failed[0])
        assert run_assemble_once(database, blobs, context, worker_id="test:assembly-recovered")
        assert service.get_project(context, project["id"])["state"] == "ready_to_export"

        with unit_of_work(database) as work:
            rows = work.connection.execute(
                """SELECT id, status, metadata FROM omnix_jobs
                    WHERE workspace_id = %s AND module = 'audiobook'
                      AND job_type = 'audiobook.assemble-chapter'
                      AND input_payload->>'project_id' = %s
                    ORDER BY created_at""",
                (context.workspace_id, project["id"]),
            ).fetchall()
            work.rollback()
        assert len(rows) == 2
        assert rows[0][1] == "failed"
        assert dict(rows[0][2]).get("superseded_by") == str(rows[1][0])
        assert rows[1][1] == "completed"
    finally:
        database.close()



def test_stale_ingest_retry_is_rejected_after_canonical_source_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-stale-ingest-retry-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Stale ingest guard")
        submission = service.submit_source(
            context, project_id=project["id"], source_format="txt",
            content=b"Chapter 1\nCanonical source.", filename="source.txt",
        )
        assert run_ingest_once(database, blobs, context, worker_id="test:stale-ingest")
        assert service.get_project(context, project["id"])["current_source_revision_id"]

        with unit_of_work(database) as work:
            work.connection.execute(
                """UPDATE omnix_jobs
                      SET status = 'failed', attempt_count = max_attempts,
                          completed_at = CURRENT_TIMESTAMP,
                          error = '{"code":"injected_stale_ingest"}'::jsonb
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, submission["job_id"]),
            )
            work.commit()

        with pytest.raises(ValueError, match="already has a canonical source"):
            service.retry_pipeline_job(
                context, project_id=project["id"], job_id=submission["job_id"],
            )
    finally:
        database.close()
