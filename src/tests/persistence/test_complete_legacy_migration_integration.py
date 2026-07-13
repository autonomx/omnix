from __future__ import annotations

import json
import os
import sqlite3
from argparse import Namespace
from pathlib import Path

import pytest

from app.persistence.blob_store import LocalBlobStore
from app.persistence.complete_cutover import CompletePostgresLegacyImporter
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.legacy_backup import create_backup, rehearse_restore
from app.persistence.legacy_export import build_bundle
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
            application_name="omnix-complete-cutover-tests",
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


def _memory_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE memory_records (
                id TEXT PRIMARY KEY, owner_type TEXT, owner_id TEXT, scope TEXT,
                scope_id TEXT, category TEXT, source TEXT, content TEXT,
                normalized_content TEXT, confidence REAL, pinned INTEGER,
                trust_level TEXT, sensitivity TEXT, provenance_type TEXT,
                provenance_id TEXT, status TEXT, revision INTEGER,
                created_at TEXT, updated_at TEXT, expires_at TEXT
            );
            CREATE TABLE memory_candidates (
                id TEXT PRIMARY KEY, owner_type TEXT, owner_id TEXT,
                source_session_id TEXT, source_message_id TEXT,
                candidate_fingerprint TEXT, proposed_scope TEXT,
                proposed_scope_id TEXT, proposed_category TEXT,
                proposed_content TEXT, confidence REAL, source TEXT,
                trust_level TEXT, sensitivity TEXT, extraction_metadata_json TEXT,
                status TEXT, created_at TEXT, resolved_at TEXT
            );
            CREATE TABLE memory_snapshots (
                id TEXT PRIMARY KEY, session_id TEXT, owner_type TEXT,
                owner_id TEXT, revision INTEGER, token_estimate INTEGER,
                created_at TEXT, refreshed_at TEXT
            );
            CREATE TABLE memory_snapshot_items (
                snapshot_id TEXT, position INTEGER, memory_record_id TEXT,
                record_revision INTEGER, frozen_content TEXT, revoked_at TEXT
            );
            CREATE TABLE memory_events (
                id INTEGER PRIMARY KEY, entity_type TEXT, entity_id TEXT,
                event_type TEXT, metadata_json TEXT, created_at TEXT
            );
            """
        )
        now = "2026-07-12T00:00:00+00:00"
        connection.execute(
            "INSERT INTO memory_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "memory:1", "system", "system-assistant", "workspace", "workspace:local",
                "project", "imported", "Remember PostgreSQL", "remember postgresql",
                1.0, 1, "unverified_import", "normal", "import", "legacy", "active",
                1, now, now, None,
            ),
        )
        connection.execute(
            "INSERT INTO memory_candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "candidate:1", "system", "system-assistant", "chat:1", "message:1",
                "fingerprint", "workspace", "workspace:local", "fact", "Candidate",
                0.5, "imported", "unverified_import", "normal", "{}", "pending", now, None,
            ),
        )
        connection.execute(
            "INSERT INTO memory_snapshots VALUES (?,?,?,?,?,?,?,?)",
            ("snapshot:1", "chat:1", "system", "system-assistant", 1, 7, now, now),
        )
        connection.execute(
            "INSERT INTO memory_snapshot_items VALUES (?,?,?,?,?,?)",
            ("snapshot:1", 0, "memory:1", 1, "Remember PostgreSQL", None),
        )
        connection.execute(
            "INSERT INTO memory_events VALUES (?,?,?,?,?,?)",
            (1, "record", "memory:1", "memory.created", "{}", now),
        )
        connection.commit()
    finally:
        connection.close()


def _jobs_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY, owner_id TEXT, module TEXT, type TEXT,
                status TEXT, resource_class TEXT, priority INTEGER,
                stages_json TEXT, progress_json TEXT, logs_json TEXT,
                input_ref_json TEXT, input_payload_json TEXT,
                output_refs_json TEXT, error_json TEXT, lease_json TEXT,
                created_at TEXT, updated_at TEXT, started_at TEXT,
                completed_at TEXT, cancel_json TEXT, compat_json TEXT
            );
            CREATE TABLE job_events (
                id INTEGER PRIMARY KEY, job_id TEXT, event_type TEXT,
                payload_json TEXT, created_at TEXT
            );
            CREATE TABLE rpg_foreground_submissions (
                session_id TEXT, submission_id TEXT, status TEXT, claim_token TEXT,
                job_id TEXT, result_json TEXT, error_text TEXT,
                lease_expires_at TEXT, execution_started_at TEXT,
                created_at TEXT, updated_at TEXT
            );
            """
        )
        now = "2026-07-12T00:00:00+00:00"
        connection.execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "job:1", None, "rpg", "rpg.foreground_turn_record", "completed", "cpu", 0,
                "[]", '{"current":1,"total":1}', "[]", '{"session_id":"campaign:1"}',
                '{"submission_id":"submission:1"}', "[]", None,
                '{"worker_id":"worker:legacy","token":"token:legacy","claimed_at":"2026-07-12T00:00:00+00:00"}',
                now, now, now, now, "{}", '{"attempt_count":1,"max_attempts":3}',
            ),
        )
        connection.execute(
            "INSERT INTO job_events VALUES (?,?,?,?,?)",
            (1, "job:1", "job.completed", '{"legacy":true}', now),
        )
        connection.execute(
            "INSERT INTO rpg_foreground_submissions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "campaign:1", "submission:1", "completed", "token:legacy", "job:1",
                '{"interaction_id":"interaction:1","ok":true}', None, now, now, now, now,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _rpg(directory: Path) -> None:
    directory.mkdir(parents=True)
    session = {
        "manifest": {"session_id": "campaign:1", "title": "Legacy campaign", "turn_count": 1},
        "state": {"scene": {"location_name": "The Rusty Flagon"}},
        "runtime_state": {"state_revision": 1, "interaction_seq": 1},
    }
    (directory / "campaign_1.json").write_text(
        json.dumps({"save_version": "legacy-v1", "session": session}),
        encoding="utf-8",
    )
    event = {
        "interaction_id": "interaction:1",
        "sequence": 1,
        "state_revision": 1,
        "submission_id": "submission:1",
        "player_input": "Hello",
        "visible_response": {"plain_text": "Hello."},
        "created_at": "2026-07-12T00:00:00+00:00",
    }
    envelope = {"format_version": "rpg_interaction_event_log_v1", "checksum": "ignored", "event": event}
    (directory / "campaign_1.interactions.jsonl").write_text(
        json.dumps(envelope) + "\n",
        encoding="utf-8",
    )


def test_real_legacy_sources_export_import_and_restore_all_lifecycle_records(tmp_path: Path) -> None:
    memory_db = tmp_path / "memory.sqlite"
    jobs_db = tmp_path / "jobs.sqlite"
    rpg_dir = tmp_path / "rpg"
    _memory_db(memory_db)
    _jobs_db(jobs_db)
    _rpg(rpg_dir)

    backup = create_backup([memory_db, jobs_db, rpg_dir], tmp_path / "backup")
    assert backup["sources"]
    restore = rehearse_restore(tmp_path / "backup")
    assert restore["ok"] is True
    assert restore["mismatches"] == []

    args = Namespace(
        source_id="local-installation:complete",
        asset_manifest=None,
        character_db=None,
        memory_db=memory_db,
        chat_db=None,
        jobs_db=jobs_db,
        rpg_sessions_dir=rpg_dir,
        settings_json=None,
        providers_json=None,
        prompts_json=None,
        research_json=None,
        reports_json=None,
        module_records_json=None,
    )
    bundle = build_bundle(args)
    assert bundle["entities"]["memory_records"][-1]["_migration_envelope"] is True
    assert bundle["entities"]["jobs"][0]["events"]
    assert bundle["entities"]["rpg_campaigns"][0]["interactions"]
    assert bundle["entities"]["rpg_campaigns"][0]["foreground_submissions"]
    assert all(item["sha256"] for item in bundle["source_inventory"] if item["exists"])

    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        importer = CompletePostgresLegacyImporter(
            database,
            blob_store=LocalBlobStore(tmp_path / "blobs"),
        )
        imported = importer.import_bundle(context, bundle)
        assert imported["ok"] is True
        with database.connection() as connection:
            counts = connection.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM omnix_memory_records), "
                "(SELECT COUNT(*) FROM omnix_memory_candidates), "
                "(SELECT COUNT(*) FROM omnix_memory_snapshots), "
                "(SELECT COUNT(*) FROM omnix_memory_snapshot_items), "
                "(SELECT COUNT(*) FROM omnix_memory_events), "
                "(SELECT COUNT(*) FROM omnix_jobs), "
                "(SELECT COUNT(*) FROM omnix_job_attempts), "
                "(SELECT COUNT(*) FROM omnix_job_events), "
                "(SELECT COUNT(*) FROM omnix_rpg_campaigns), "
                "(SELECT COUNT(*) FROM omnix_rpg_turns), "
                "(SELECT COUNT(*) FROM omnix_rpg_interactions), "
                "(SELECT COUNT(*) FROM omnix_rpg_foreground_submissions), "
                "(SELECT COUNT(*) FROM omnix_rpg_snapshots)"
            ).fetchone()
        values = tuple(int(value) for value in counts)
        assert values[0:7] == (1, 1, 1, 1, 1, 1, 1)
        assert values[7] >= 2
        assert values[8:] == (1, 1, 1, 1, 1)
    finally:
        database.close()
