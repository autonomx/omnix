from __future__ import annotations

import os

import pytest

from app.audiobook.service import AudiobookService
from app.audiobook.worker import run_analyze_once, run_ingest_once
from app.audiobook.review_repository import PostgresAudiobookReviewRepository
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


def test_document_structure_migration_is_append_only_policy_extension() -> None:
    migration = next(
        item for item in discover_migrations()
        if item.version == "0093_audiobook_document_structure"
    )
    assert "omnix_audiobook_structure_runs" in migration.sql
    assert "omnix_audiobook_document_blocks" in migration.sql
    assert "omnix_audiobook_structural_regions" in migration.sql
    assert "omnix_audiobook_document_overrides" in migration.sql
    assert "audiobook_structure_run_immutable" in migration.sql
    assert "audiobook_document_block_immutable" in migration.sql
    assert "audiobook_structural_region_immutable" in migration.sql
    assert "audiobook_document_override_immutable" in migration.sql


def test_ingest_persists_structure_and_scoped_override_history(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.audiobook.worker.local_structure_classifier", lambda: None
    )
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"],
        pool_min=1,
        pool_max=3,
        connect_timeout_seconds=10,
        statement_timeout_ms=30_000,
        lock_timeout_ms=5_000,
        application_name="omnix-audiobook-document-structure-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Structure Test")
        assert service.get_project(
            context, project["id"]
        )["audiobook_mode"] == "story_only"

        service.submit_source(
            context,
            project_id=project["id"],
            source_format="txt",
            content=(
                b"Page 1 of 2\n"
                b"Chapter One\n"
                b"Daniel entered the market.\n"
            ),
            filename="structure.txt",
        )
        assert run_ingest_once(
            database, blobs, context, worker_id="test:structure-ingest"
        )

        structure = service.get_document_structure(
            context, project_id=project["id"]
        )
        assert structure["run_id"]
        assert structure["document_structure_version"] == "document-role-v1"
        assert structure["blocks"]
        page = next(
            item for item in structure["blocks"]
            if item["original_text"] == "Page 1 of 2"
        )
        assert page["effective_role"] == "page_number"
        assert page["render_action"] == "SKIP"
        assert page["analysis_visibility"]["speaker_attribution"] == "EXCLUDE"
        assert page["provenance"]

        mode = service.set_audiobook_mode(
            context, project_id=project["id"], mode="verbatim"
        )
        assert mode["audiobook_mode"] == "verbatim"
        verbatim = service.get_document_structure(
            context, project_id=project["id"]
        )
        page = next(
            item for item in verbatim["blocks"]
            if item["original_text"] == "Page 1 of 2"
        )
        assert page["render_action"] == "READ"

        with pytest.raises(ValueError, match="current structure analysis"):
            service.set_document_override(
                context,
                project_id=project["id"],
                scope="BLOCK",
                scope_key="ab:db:not-current",
                action="READ",
            )
        with pytest.raises(ValueError, match="current structure analysis"):
            service.set_document_override(
                context,
                project_id=project["id"],
                scope="DOCUMENT_ROLE",
                scope_key="not_a_document_role",
                action="SKIP",
            )

        first = service.set_document_override(
            context,
            project_id=project["id"],
            scope="BLOCK",
            scope_key=page["id"],
            action="SKIP",
        )
        second = service.set_document_override(
            context,
            project_id=project["id"],
            scope="BLOCK",
            scope_key=page["id"],
            action="READ",
        )
        assert second["revision"] == first["revision"] + 1
        assert first["reanalysis_required"] is False
        assert first["analysis_job_id"] is None
        assert second["reanalysis_required"] is False
        assert second["analysis_job_id"] is None

        latest = service.get_document_structure(
            context, project_id=project["id"]
        )
        page = next(
            item for item in latest["blocks"]
            if item["original_text"] == "Page 1 of 2"
        )
        assert page["render_action"] == "READ"
        matching = [
            item for item in latest["overrides"]
            if item["scope"] == "BLOCK" and item["scope_key"] == page["id"]
        ]
        assert len(matching) == 1
        assert matching[0]["revision"] == second["revision"]

        with unit_of_work(database) as work:
            row = work.connection.execute(
                """SELECT id, structure_run_id
                     FROM omnix_audiobook_document_blocks
                    WHERE workspace_id = %s AND id = %s
                    LIMIT 1""",
                (context.workspace_id, page["id"]),
            ).fetchone()
            with pytest.raises(Exception):
                work.connection.execute(
                    """UPDATE omnix_audiobook_document_blocks
                          SET content_role = 'story_text'
                        WHERE workspace_id = %s AND id = %s
                          AND structure_run_id = %s""",
                    (context.workspace_id, row[0], row[1]),
                )
            work.rollback()
    finally:
        database.close()



def test_render_run_omits_fully_skipped_source_chapters(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.audiobook.worker.local_structure_classifier", lambda: None
    )
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    monkeypatch.setattr(
        "app.audiobook.service.assert_model_revision",
        lambda _provider, _model, _revision: None,
    )
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"],
        pool_min=1,
        pool_max=3,
        connect_timeout_seconds=10,
        statement_timeout_ms=30_000,
        lock_timeout_ms=5_000,
        application_name="omnix-audiobook-skipped-chapter-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Skipped chapter test")

        service.submit_source(
            context,
            project_id=project["id"],
            source_format="md",
            content=(
                "# Contents\n"
                "Chapter One ........ 1\n"
                "# Chapter One\n"
                "Daniel opened the gate.\n"
            ).encode(),
            filename="skipped.md",
        )
        assert run_ingest_once(
            database, blobs, context, worker_id="test:skipped-ingest"
        )
        assert run_analyze_once(
            database, context, worker_id="test:skipped-analysis"
        )
        detail = service.get_project(context, project["id"])
        assert detail["state"] == "ready_to_render"
        assert len(detail["chapters"]) == 2

        narrator = next(
            item for item in detail["speakers"] if item["kind"] == "narrator"
        )
        with unit_of_work(database) as work:
            PostgresAudiobookReviewRepository(work.connection).assign_voice(
                context,
                project_id=project["id"],
                speaker_id=narrator["id"],
                voice_profile_id="voice-cloning:skipped-chapter-test",
                voice_revision_hash="a" * 64,
            )
            work.commit()

        render = service.start_render(
            context,
            project_id=project["id"],
            model_revision="skipped-chapter-test-model",
        )
        assert render["source_chapter_count"] == 2
        assert render["chapter_count"] == 1
        assert render["skipped_chapter_count"] == 1
        assert len(render["skipped_chapter_ids"]) == 1

        with unit_of_work(database) as work:
            rows = work.connection.execute(
                """SELECT input_payload->>'chapter_id'
                     FROM omnix_jobs
                    WHERE workspace_id = %s
                      AND module = 'audiobook'
                      AND job_type = 'audiobook.render-chapter'
                      AND input_payload->>'render_run_id' = %s""",
                (context.workspace_id, render["render_run_id"]),
            ).fetchall()
            work.rollback()
        assert len(rows) == 1
        assert str(rows[0][0]) not in set(render["skipped_chapter_ids"])
    finally:
        database.close()



def test_role_override_requeues_analysis_when_speaker_visibility_changes(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.audiobook.worker.local_structure_classifier", lambda: None
    )
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"],
        pool_min=1,
        pool_max=3,
        connect_timeout_seconds=10,
        statement_timeout_ms=30_000,
        lock_timeout_ms=5_000,
        application_name="omnix-audiobook-role-override-test",
    ))
    try:
        apply_migrations(database)
        context = bootstrap_local_tenant(database)
        blobs = LocalBlobStore(tmp_path / "blobs")
        service = AudiobookService(database, blobs)
        project = service.create_project(context, title="Role override test")

        service.submit_source(
            context,
            project_id=project["id"],
            source_format="txt",
            content=b"North Gate\nDaniel crossed the bridge.\n",
            filename="role.txt",
        )
        assert run_ingest_once(
            database, blobs, context, worker_id="test:role-ingest"
        )
        assert run_analyze_once(
            database, context, worker_id="test:role-analysis"
        )
        assert service.get_project(context, project["id"])["state"] == "ready_to_render"
        structure = service.get_document_structure(
            context, project_id=project["id"]
        )
        block = next(
            item for item in structure["blocks"]
            if item["original_text"] == "North Gate"
        )
        assert block["effective_role"] == "unknown"
        assert block["analysis_visibility"]["speaker_attribution"] == "INCLUDE"

        changed = service.set_document_override(
            context,
            project_id=project["id"],
            scope="BLOCK",
            scope_key=block["id"],
            action="DEFAULT",
            role_override="preface",
        )
        assert changed["reanalysis_required"] is True
        assert changed["analysis_job_id"]
        assert service.get_project(context, project["id"])["state"] == "analyzing"

        with unit_of_work(database) as work:
            row = work.connection.execute(
                """SELECT input_payload, metadata, status
                     FROM omnix_jobs
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, changed["analysis_job_id"]),
            ).fetchone()
            work.rollback()
        assert row is not None
        assert row[0]["force_reclassify"] is True
        assert row[0]["source_revision_id"] == structure["source_revision_id"]
        assert row[1]["reason"] == "document_role_override"
        assert row[2] == "queued"

        # Clearing a prior role override can restore a different speaker-analysis
        # visibility and therefore must trigger the same reanalysis contract.
        with unit_of_work(database) as work:
            work.connection.execute(
                """UPDATE omnix_jobs
                      SET status = 'canceled', completed_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, changed["analysis_job_id"]),
            )
            work.connection.execute(
                """UPDATE omnix_audiobook_projects
                      SET state = 'ready_to_render'
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, project["id"]),
            )
            work.commit()

        reset = service.set_document_override(
            context,
            project_id=project["id"],
            scope="BLOCK",
            scope_key=block["id"],
            action="DEFAULT",
            role_override=None,
        )
        assert reset["reanalysis_required"] is True
        assert reset["analysis_job_id"]
        assert reset["analysis_job_id"] != changed["analysis_job_id"]
        reset_structure = service.get_document_structure(
            context, project_id=project["id"]
        )
        reset_block = next(
            item for item in reset_structure["blocks"]
            if item["id"] == block["id"]
        )
        assert reset_block["effective_role"] == "unknown"
        assert reset_block["analysis_visibility"]["speaker_attribution"] == "INCLUDE"
    finally:
        database.close()
