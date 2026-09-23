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
