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
            "omnix_assets, omnix_settings_entries, omnix_settings, omnix_secret_references, "
            "omnix_audit_events, omnix_idempotency_keys, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )
        connection.execute(
            """
            UPDATE omnix_persistence_cutover
               SET mode = 'legacy_preflight', authority_state = 'legacy_preflight',
                   import_run_id = NULL,
                   source_hash = NULL, activated_at = NULL,
                   rollback_recorded_at = NULL, metadata = '{}'::jsonb,
                   updated_at = CURRENT_TIMESTAMP
             WHERE singleton = TRUE
            """
        )


def _restore_runtime_authority() -> None:
    database = _database()
    try:
        with database.transaction() as connection:
            connection.execute(
                "UPDATE omnix_persistence_cutover "
                "SET mode = 'postgresql', authority_state = 'postgresql_stabilized', "
                "updated_at = CURRENT_TIMESTAMP WHERE singleton = TRUE"
            )
    finally:
        database.close()


_RUNTIME_SCRIPT = r'''
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.persistence.startup import bootstrap_postgresql_runtime
from app.errors import LegacyPersistenceRetired
status = bootstrap_postgresql_runtime()
assert status.ready is True
assert status.backend == "postgresql"
assert status.cutover_mode == "postgresql"

connection = sqlite3.connect(":memory:")
connection.close()
# Production does not mutate the standard library. Domain factories remain PostgreSQL-only.

from app.persistence.database import default_database
from app.security.tenant_context import current_tenant
from app.settings.access import (
    install_settings_service,
    load_secrets,
    load_settings,
    save_secrets,
    save_settings,
)
from app.settings.registry import core_setting_specs
from app.platform.assistant_memory.persistence.settings_store import assistant_memory_setting_spec
from app.settings.service import SettingRevisionConflict, SettingsService

settings_service = SettingsService(
    default_database(), current_tenant, specs=core_setting_specs()
)
install_settings_service(settings_service)
settings_service.register_specs((assistant_memory_setting_spec(),))
save_settings({
    "provider": "lmstudio",
    "lmstudio": {
        "base_url": "http://localhost:1234",
        "direct": False,
        "model": "runtime-model",
    },
})
assert load_settings()["lmstudio"]["model"] == "runtime-model"
try:
    settings_service.set("provider", "cerebras", expected_revision=0)
except SettingRevisionConflict:
    pass
else:
    raise AssertionError("a stale settings revision unexpectedly overwrote the provider")
assert settings_service.get("provider")["value"] == "lmstudio"
with default_database().connection() as connection:
    assert connection.execute(
        "SELECT COUNT(*) FROM omnix_module_records "
        "WHERE module = 'platform' AND record_type = 'settings'"
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM omnix_settings"
    ).fetchone()[0] == 0
assert load_secrets() == {
    "api_keys": {
        "openrouter": "runtime-openrouter-key",
        "cerebras": "runtime-cerebras-key",
    }
}
save_secrets({"api_keys": {"openrouter": "environment-cannot-be-overridden"}})
assert load_secrets() == {
    "api_keys": {
        "openrouter": "runtime-openrouter-key",
        "cerebras": "runtime-cerebras-key",
    }
}
protected_provider_keys = Path(os.environ["OMNIX_PROVIDER_SECRETS_PATH"])
assert protected_provider_keys.exists()
assert b"environment-cannot-be-overridden" not in protected_provider_keys.read_bytes()

from app.platform.assistant_tools.credentials import (
    AssistantToolCredentialsPayload,
    load_assistant_tool_credentials,
    save_assistant_tool_credentials,
)

from app.security.secrets import SecretStoreUnavailable

# Credentials go to the secret store only (WP-4.9); with the read-only env
# store, saving fails closed and nothing is written in plaintext.
assert load_assistant_tool_credentials().credentials == []
try:
    save_assistant_tool_credentials(AssistantToolCredentialsPayload())
except SecretStoreUnavailable:
    pass
else:
    raise AssertionError("assistant-tool credentials were saved without a writable secret store")

from app.platform.chat.assist.house import load_house_state, save_house_state

save_house_state({"rooms": {"office": {"lights": "on"}}, "reminders": []})
assert load_house_state()["rooms"]["office"]["lights"] == "on"

from app.platform.chat.assistant_turns import default_assistant_turn_coordinator

assistant_turn = default_assistant_turn_coordinator().start(
    session_id="chat:runtime",
    user_message_id="message:runtime",
    user_turn_id="turn:runtime",
)
assert default_assistant_turn_coordinator().get(assistant_turn.assistant_turn_id) is not None

from app.platform.assistant_memory.settings import (
    AssistantMemorySettingsUpdate,
)

from app.platform.assistant_memory.settings import default_memory_settings_store
memory_settings = default_memory_settings_store()
memory_settings.update(AssistantMemorySettingsUpdate(suggestions_enabled=True))
assert memory_settings.load_persisted().suggestions_enabled is True
with default_database().connection() as connection:
    assert connection.execute(
        "SELECT COUNT(*) FROM omnix_settings_entries "
        "WHERE key = 'assistant_memory.runtime'"
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM omnix_module_records "
        "WHERE module = 'assistant-memory' AND record_type = 'runtime-settings'"
    ).fetchone()[0] == 0

from app.platform.characters.live_conversation_profile import (
    LiveConversationProfileUpdate,
    default_live_conversation_profile_store,
)

conversation_profiles = default_live_conversation_profile_store()
conversation_profiles.update_defaults(LiveConversationProfileUpdate(talkativeness=63))
assert conversation_profiles.get_defaults().talkativeness == 63

from app.platform.assistant_tools.ledger import (
    AssistantToolLedgerEntry,
    append_assistant_tool_ledger_entry,
    load_assistant_tool_ledger,
)

ledger_entry = append_assistant_tool_ledger_entry(
    AssistantToolLedgerEntry(tool_id="tool:runtime", action_id="action:runtime")
)
assert load_assistant_tool_ledger().entries[0].execution_id == ledger_entry.execution_id

for variable in (
    "OMNIX_ASSISTANT_TURN_STORE_PATH",
    "OMNIX_LIVE_CONVERSATION_PROFILE_PATH",
    "OMNIX_ASSISTANT_TOOLS_LEDGER_PATH",
    "OMNIX_ASSISTANT_TOOLS_CREDENTIALS_PATH",
    "OMNIX_ASSISTANT_TOOLS_OAUTH_CLIENTS_PATH",
):
    assert not Path(os.environ[variable]).exists(), variable

from app.platform.chat.models import ChatMessage, ChatSession
from app.platform.chat.persistence.chat_store import PostgresChatRepositoryAdapter
from app.runtime.feature_catalog import load_feature
from app.persistence.repository_registry import install_repository_specs

install_repository_specs(tuple(load_feature("chat").repositories))

now = datetime.now(timezone.utc).isoformat()
chat_repository = PostgresChatRepositoryAdapter()
chat_repository.create_session(
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
)
loaded_chat = chat_repository.get_session("chat:runtime")
assert loaded_chat is not None
assert loaded_chat.messages[0].content == "hello"

from app.platform.characters.models import CreateCharacterRequest
from app.platform.characters.persistence.character_store import PostgresCharacterRepositoryAdapter

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

from app.conversation.memory_contracts import MemoryRecord
from app.platform.assistant_memory.persistence.memory_store import PostgresMemoryRepositoryAdapter

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
from app.persistence.job_store import PostgresJobStoreAdapter

jobs = PostgresJobStoreAdapter()
job = jobs.create_job(CreateJobRequest(
    module="runtime-test",
    type="runtime.verify",
    resource_class=ResourceClass.CPU,
    input_payload={"safe": True},
))
assert jobs.get_job(job.id).id == job.id

from app.assets.models import AssetRecord, AssetType
from app.persistence.shared_asset_store import PostgresSharedAssetStoreAdapter

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

from app.apps.rpg.foundation.persistence.rpg_compat import load_session_from_postgres, save_session_to_postgres

session = {
    "manifest": {"session_id": "campaign:runtime", "title": "Runtime campaign", "turn_count": 0},
    "state": {"scene": {"location_name": "The Rusty Flagon"}},
    "runtime_state": {"state_revision": 0, "interaction_seq": 0},
}
save_session_to_postgres(session)
assert load_session_from_postgres("campaign:runtime") == session

from app import assets as assets_package
from app.assets import store as asset_store_module
from app.platform.assistant_memory import service as memory_service_module
from app.platform.characters import service as character_service_module
from app.platform.chat import repository as chat_repository_module
from app.composition.runtime_composition import production_job_store

assert chat_repository_module.InMemoryChatRepository.__name__ == "InMemoryChatRepository"
assert memory_service_module.InMemoryMemoryRepository.__name__ == "InMemoryMemoryRepository"
assert character_service_module.CharacterRepository.__name__ == "InMemoryCharacterRepository"
assert asset_store_module.SharedAssetStore.__name__ == "SharedAssetStore"
assert assets_package.SharedAssetStore.__name__ == "SharedAssetStore"
assert production_job_store().__class__.__name__ == "PostgresJobStoreAdapter"

print("runtime-postgresql-cutover-ok")
'''


def test_explicit_application_bootstrap_uses_postgresql_and_rejects_sqlite(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    request.addfinalizer(_restore_runtime_authority)
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
            "OMNIX_ASSISTANT_TURN_STORE_PATH": str(tmp_path / "assistant-turns.json"),
            "OMNIX_LIVE_CONVERSATION_PROFILE_PATH": str(tmp_path / "conversation-profiles.json"),
            "OMNIX_ASSISTANT_TOOLS_LEDGER_PATH": str(tmp_path / "assistant-tools-ledger.jsonl"),
            "OMNIX_SECRET_STORE": "env",
            # Former plaintext locations: they must never be created.
            "OMNIX_ASSISTANT_TOOLS_CREDENTIALS_PATH": str(tmp_path / "assistant-tool-credentials.json"),
            "OMNIX_ASSISTANT_TOOLS_OAUTH_CLIENTS_PATH": str(tmp_path / "assistant-tool-oauth-clients.json"),
            "OMNIX_PROVIDER_SECRETS_PATH": str(tmp_path / "provider-api-keys.dpapi"),
            "OPENROUTER_API_KEY": "runtime-openrouter-key",
            "CEREBRAS_API_KEY": "runtime-cerebras-key",
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
