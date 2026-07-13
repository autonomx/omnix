from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.persistence.blob_store import LocalBlobStore
from app.persistence.config import DatabaseSettings
from app.persistence.cutover import (
    LEGACY_BUNDLE_FORMAT,
    LegacyBundleError,
    LegacySourceChanged,
    PostgresLegacyImporter,
    bundle_hash,
    preflight_bundle,
)
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=8,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-cutover-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_legacy_import_items, omnix_legacy_import_runs, "
            "omnix_runtime_projections, omnix_module_records, omnix_reports, "
            "omnix_research_records, omnix_prompt_templates, "
            "omnix_provider_status_projections, omnix_provider_configs, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, "
            "omnix_rpg_foreground_submissions, omnix_outbox_events, "
            "omnix_dead_letters, omnix_job_events, omnix_job_attempts, omnix_jobs, "
            "omnix_chat_messages, omnix_chat_sessions, omnix_memory_snapshot_items, "
            "omnix_memory_snapshots, omnix_memory_candidates, omnix_memory_events, "
            "omnix_memory_records, omnix_conversation_segments, "
            "omnix_character_versions, omnix_characters, omnix_asset_versions, "
            "omnix_assets, omnix_settings, omnix_secret_references, "
            "omnix_audit_events, omnix_idempotency_keys, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )
        connection.execute(
            """
            UPDATE omnix_persistence_cutover
               SET mode = 'legacy_preflight', import_run_id = NULL,
                   source_hash = NULL, activated_at = NULL,
                   rollback_recorded_at = NULL, metadata = '{}'::jsonb,
                   updated_at = CURRENT_TIMESTAMP
             WHERE singleton = TRUE
            """
        )


def _bundle(tmp_path: Path) -> dict:
    asset_file = tmp_path / "legacy-report.json"
    asset_file.write_text("{}", encoding="utf-8")
    bundle = {
        "format_version": LEGACY_BUNDLE_FORMAT,
        "source_id": "local-installation:test",
        "created_at": "2026-07-12T00:00:00+00:00",
        "source_paths": {"synthetic": str(tmp_path)},
        "entities": {
            "assets": [
                {
                    "id": "asset:legacy-report",
                    "module": "reports",
                    "asset_type": "report",
                    "mime_type": "application/json",
                    "source_path": str(asset_file),
                    "storage_key": "legacy/reports/report.json",
                    "metadata": {"legacy": True},
                }
            ],
            "characters": [
                {
                    "id": "character:maya",
                    "profile": {"display_name": "Maya", "description": "Current"},
                    "versions": [
                        {
                            "version": 1,
                            "profile": {"display_name": "Maya", "description": "Original"},
                        },
                        {
                            "version": 2,
                            "profile": {"display_name": "Maya", "description": "Current"},
                        },
                    ],
                }
            ],
            "memory_records": [
                {
                    "id": "memory:legacy",
                    "owner_type": "user",
                    "owner_id": "user:local",
                    "category": "project",
                    "content": "PostgreSQL is authoritative",
                    "source": "legacy",
                }
            ],
            "chat_sessions": [
                {
                    "id": "chat:legacy",
                    "title": "Legacy chat",
                    "messages": [
                        {"id": "message:1", "role": "user", "content": "Hello"},
                        {
                            "id": "message:2",
                            "role": "assistant",
                            "content": "Hello from the imported transcript",
                        },
                    ],
                }
            ],
            "jobs": [
                {
                    "id": "job:legacy-report",
                    "module": "reports",
                    "job_type": "report.generate",
                    "resource_class": "cpu",
                    "status": "completed",
                    "output_refs": [{"asset_id": "asset:legacy-report"}],
                    "progress": {"current": 1, "total": 1},
                    "attempt_count": 1,
                    "completed_at": "2026-07-12T00:00:00+00:00",
                }
            ],
            "rpg_campaigns": [
                {
                    "id": "campaign:legacy",
                    "title": "Legacy campaign",
                    "revision": 3,
                    "state": {
                        "manifest": {"turn_count": 3},
                        "state": {"scene": {"location_name": "The Rusty Flagon"}},
                        "runtime_state": {"state_revision": 3},
                    },
                    "engine_version": "legacy-engine",
                    "schema_version": "legacy-save-v1",
                    "seed": "legacy-seed",
                }
            ],
            "settings": [
                {
                    "scope": "application",
                    "key": "theme",
                    "value": {"mode": "dark"},
                }
            ],
            "providers": [
                {
                    "id": "provider:lmstudio",
                    "provider_type": "openai-compatible",
                    "display_name": "LM Studio",
                    "config": {"base_url": "http://127.0.0.1:1234/v1"},
                }
            ],
            "prompts": [
                {
                    "id": "prompt:legacy",
                    "name": "Legacy prompt",
                    "template_type": "system",
                    "content": "Remain grounded.",
                }
            ],
            "research_records": [
                {
                    "id": "research:legacy",
                    "research_type": "web",
                    "query_text": "PostgreSQL",
                    "result": {"sources": 2},
                }
            ],
            "reports": [
                {
                    "id": "report:legacy",
                    "report_type": "migration",
                    "title": "Legacy migration",
                    "summary": {"ok": True},
                    "blob_asset_id": "asset:legacy-report",
                    "generated_by_job_id": "job:legacy-report",
                }
            ],
            "module_records": [
                {
                    "id": "policy:legacy",
                    "module": "assist-core",
                    "record_type": "policy",
                    "payload": {"approval_required": True},
                }
            ],
        },
    }
    bundle["source_hash"] = bundle_hash(bundle)
    return bundle


def test_bundle_preflight_counts_hashes_and_rejects_secrets(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    report = preflight_bundle(bundle)
    assert report["ok"] is True
    assert report["source_hash"] == bundle["source_hash"]
    assert report["counts"]["chat_sessions"] == 1
    assert report["counts"]["assets"] == 1

    unsafe = _bundle(tmp_path)
    unsafe["source_id"] = "unsafe"
    unsafe["entities"]["providers"][0]["config"]["api_key"] = "secret"
    unsafe["source_hash"] = bundle_hash(unsafe)
    unsafe_report = preflight_bundle(unsafe)
    assert unsafe_report["ok"] is False
    assert any("secret-bearing" in error for error in unsafe_report["errors"])


def test_end_to_end_import_is_verified_resumable_and_cutover_gated(tmp_path: Path) -> None:
    database = _database()
    store = LocalBlobStore(tmp_path / "blobs")
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        importer = PostgresLegacyImporter(database, blob_store=store)
        bundle = _bundle(tmp_path)

        dry_run = importer.import_bundle(context, bundle, dry_run=True)
        assert dry_run["ok"] is True
        assert dry_run["preflight"]["counts"]["characters"] == 1

        imported = importer.import_bundle(context, bundle)
        assert imported["ok"] is True
        assert imported["already_completed"] is False
        assert imported["verification"]["ok"] is True
        run_id = imported["run"]["id"]

        replay = importer.import_bundle(context, bundle)
        assert replay["ok"] is True
        assert replay["already_completed"] is True
        assert replay["run"]["id"] == run_id

        status_before = importer.cutover_status()
        assert status_before["mode"] == "legacy_preflight"
        active = importer.activate_cutover(
            run_id=run_id,
            metadata={"operator": "test", "backup_verified": True},
        )
        assert active["mode"] == "postgresql"
        assert active["source_hash"] == bundle["source_hash"]
        assert active["metadata"]["backup_verified"] is True

        rollback = importer.record_rollback(
            run_id=run_id,
            reason="synthetic rollback rehearsal",
        )
        assert rollback["mode"] == "rollback_recorded"
        assert rollback["metadata"]["rollback_reason"] == "synthetic rollback rehearsal"

        with database.connection() as connection:
            counts = connection.execute(
                "SELECT (SELECT COUNT(*) FROM omnix_assets), "
                "(SELECT COUNT(*) FROM omnix_characters), "
                "(SELECT COUNT(*) FROM omnix_character_versions), "
                "(SELECT COUNT(*) FROM omnix_memory_records), "
                "(SELECT COUNT(*) FROM omnix_chat_sessions), "
                "(SELECT COUNT(*) FROM omnix_chat_messages), "
                "(SELECT COUNT(*) FROM omnix_jobs), "
                "(SELECT COUNT(*) FROM omnix_rpg_campaigns), "
                "(SELECT COUNT(*) FROM omnix_settings), "
                "(SELECT COUNT(*) FROM omnix_provider_configs), "
                "(SELECT COUNT(*) FROM omnix_prompt_templates), "
                "(SELECT COUNT(*) FROM omnix_research_records), "
                "(SELECT COUNT(*) FROM omnix_reports), "
                "(SELECT COUNT(*) FROM omnix_module_records)"
            ).fetchone()
        assert tuple(int(value) for value in counts) == (
            1,
            1,
            2,
            1,
            1,
            2,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
        )
        assert store.read_bytes("legacy/reports/report.json") == b"{}"
    finally:
        database.close()


def test_changed_source_id_is_rejected_after_import(tmp_path: Path) -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        importer = PostgresLegacyImporter(
            database, blob_store=LocalBlobStore(tmp_path / "blobs")
        )
        bundle = _bundle(tmp_path)
        assert importer.import_bundle(context, bundle)["ok"] is True

        changed = _bundle(tmp_path)
        changed["entities"]["module_records"][0]["payload"]["approval_required"] = False
        changed["source_hash"] = bundle_hash(changed)
        with pytest.raises(LegacySourceChanged):
            importer.import_bundle(context, changed)
    finally:
        database.close()


def test_failed_item_is_reported_and_does_not_activate_cutover(tmp_path: Path) -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        importer = PostgresLegacyImporter(
            database, blob_store=LocalBlobStore(tmp_path / "blobs")
        )
        bundle = _bundle(tmp_path)
        bundle["source_id"] = "local-installation:missing-asset"
        bundle["entities"]["assets"][0]["source_path"] = str(tmp_path / "missing.json")
        bundle["source_hash"] = bundle_hash(bundle)

        result = importer.import_bundle(context, bundle)
        assert result["ok"] is False
        assert result["run"]["status"] == "failed"
        assert result["verification"]["ok"] is False
        assert result["errors"][0]["entity_type"] == "assets"
        with pytest.raises(Exception):
            importer.activate_cutover(run_id=result["run"]["id"])
    finally:
        database.close()


def test_declared_hash_drift_fails_preflight(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    bundle["source_hash"] = "0" * 64
    with pytest.raises(LegacyBundleError):
        database = _database()
        try:
            importer = PostgresLegacyImporter(
                database, blob_store=LocalBlobStore(tmp_path / "blobs")
            )
            context = bootstrap_local_tenant(database)
            importer.import_bundle(context, bundle, dry_run=True)
        finally:
            database.close()
