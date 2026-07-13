from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
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
            application_name="omnix-runtime-retirement-tests",
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


_RUNTIME_SCRIPT = r'''
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.persistence.startup import bootstrap_postgresql_runtime
from app.persistence.runtime import LegacyPersistenceRetired
from app.persistence.runtime_install import runtime_adapters_installed

status = bootstrap_postgresql_runtime()
assert status.ready is True
assert status.backend == "postgresql"
assert status.cutover_mode == "postgresql"
assert runtime_adapters_installed() is True

try:
    sqlite3.connect(":memory:")
except LegacyPersistenceRetired:
    pass
else:
    raise AssertionError("SQLite connection unexpectedly remained available")

from app.chat.models import ChatMessage, ChatSession
from app.persistence.chat_compat import PostgresChatRepositoryAdapter

now = datetime.now(timezone.utc).isoformat()
chat_repository = PostgresChatRepositoryAdapter()
chat_repository.save_sessions([
    ChatSession(
        id="chat:runtime",
        title="Runtime PostgreSQL",
        provider_id=None,
        model_id=None,
        profile_id="profile:default",
        workspace_id="workspace:local",
        interaction_mode="system",
        transcript_policy="persistent",
        created_at=now,
        updated_at=now,
        messages=[ChatMessage(id="message:runtime", role="user", content="hello", created_at=now)],
    )
])
loaded_chats = chat_repository.load_sessions()
assert len(loaded_chats) == 1
assert loaded_chats[0].messages[0].content == "hello"

from app.characters.models import CreateCharacterRequest
from app.persistence.character_compat import PostgresCharacterRepositoryAdapter

characters = PostgresCharacterRepositoryAdapter()
created_character = characters.create(CreateCharacterRequest(
    id="character:runtime",
    display_name="Runtime",
    description="PostgreSQL character",
    personality_prompt="Remain grounded.",
    default_greeting="Hello.",
))
assert created_character.active_version == 1
assert characters.get(created_character.id) is not None

from app.assistant_memory.models import MemoryRecord
from app.persistence.memory_compat import PostgresMemoryRepositoryAdapter

memories = PostgresMemoryRepositoryAdapter()
record = MemoryRecord(
    id="memory:runtime",
    owner_type="system",
    owner_id="system-assistant",
    scope="workspace",
    scope_id="workspace:local",
    category="project",
    source="user_saved",
    content="PostgreSQL is authoritative",
    normalized_content="postgresql is authoritative",
    confidence=1.0,
    pinned=True,
    trust_level="user_approved",
    sensitivity="normal",
    provenance_type="system",
    provenance_id="runtime-test",
    status="active",
    revision=1,
    created_at=now,
    updated_at=now,
)
memories.create_record(record)
assert memories.get_record("memory:runtime").content == "PostgreSQL is authoritative"

from app.jobs.models import CreateJobRequest, ResourceClass
from app.persistence.job_compat import PostgresJobStoreAdapter

jobs = PostgresJobStoreAdapter()
job = jobs.create_job(CreateJobRequest(
    module="runtime-test",
    type="runtime.verify",
    resource_class=ResourceClass.CPU,
    input_payload={"safe": True},
))
assert jobs.get_job(job.id).id == job.id

from app.assets.models import AssetRecord, AssetType
from app.persistence.asset_compat import PostgresSharedAssetStoreAdapter

with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / "runtime.txt"
    source.write_text("runtime", encoding="utf-8")
    assets = PostgresSharedAssetStoreAdapter()
    stored_asset = assets.upsert_asset(AssetRecord(
        id="asset:runtime",
        module="runtime-test",
        type=AssetType.REPORT,
        mime_type="text/plain",
        storage_path=str(source),
        metadata={"safe": True},
        created_at=now,
    ))
    assert stored_asset.id == "asset:runtime"
    assert any(item.id == "asset:runtime" for item in assets.list_assets().assets)

from app.persistence.rpg_compat import load_session_from_postgres, save_session_to_postgres

session = {
    "manifest": {"session_id": "campaign:runtime", "title": "Runtime campaign", "turn_count": 0},
    "state": {"scene": {"location_name": "The Rusty Flagon"}},
    "runtime_state": {"state_revision": 0, "interaction_seq": 0},
}
save_session_to_postgres(session)
assert load_session_from_postgres("campaign:runtime") == session

from app import assets as assets_package
from app.assets import store as asset_store_module
from app.assistant_memory import service as memory_service_module
from app.characters import service as character_service_module
from app.chat import store as chat_store_module
from app.jobs import store as job_store_module

assert chat_store_module.SQLiteChatRepository.__name__ == "PostgresChatRepositoryAdapter"
assert memory_service_module.SQLiteMemoryRepository.__name__ == "PostgresMemoryRepositoryAdapter"
assert character_service_module.CharacterRepository.__name__ == "PostgresCharacterRepositoryAdapter"
assert asset_store_module.SharedAssetStore.__name__ == "PostgresSharedAssetStoreAdapter"
assert assets_package.SharedAssetStore.__name__ == "PostgresSharedAssetStoreAdapter"
assert job_store_module.default_job_store().__class__.__name__ == "PostgresJobStoreAdapter"

print("runtime-postgresql-cutover-ok")
'''


def test_explicit_application_bootstrap_uses_postgresql_and_rejects_sqlite(tmp_path: Path) -> None:
    database = _database()
    try:
        _reset(database)
    finally:
        database.close()

    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONPATH": "src",
            "OMNIX_DATABASE_URL": os.environ["OMNIX_TEST_DATABASE_URL"],
            "OMNIX_PERSISTENCE_MODE": "postgresql",
            "OMNIX_BLOB_ROOT": str(tmp_path / "blobs"),
        }
    )
    environment.pop("OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE", None)
    result = subprocess.run(
        [sys.executable, "-c", _RUNTIME_SCRIPT],
        cwd=Path(__file__).resolve().parents[3],
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    assert "runtime-postgresql-cutover-ok" in result.stdout
