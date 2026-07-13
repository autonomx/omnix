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
            application_name="omnix-active-feature-factory-tests",
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


_SCRIPT = r'''
from datetime import datetime, timezone
from types import SimpleNamespace

from app.persistence.startup import bootstrap_postgresql_runtime
bootstrap_postgresql_runtime()

from app.assist_core import policy_store
policy_store.write_pending({"confirmation:1": {"status": "pending"}})
assert policy_store.read_pending()["confirmation:1"]["status"] == "pending"

from app.assistant_tools import config_store
config = config_store.load_assistant_tools_config()
saved = config_store.save_assistant_tools_config(config)
assert saved.model_dump(mode="json") == config.model_dump(mode="json")

from app.gateway import live_chat_evaluation_store as evaluations
assert evaluations.LiveChatEvaluationStore.__name__ == "PostgresLiveChatEvaluationStore"
store = evaluations.default_live_chat_evaluation_store()
record = store.upsert(evaluations.VoiceSessionEvaluationCreate(
    call_id="call:postgresql",
    session_id="chat:factory",
    started_at="2026-07-12T00:00:00+00:00",
    ended_at="2026-07-12T00:01:00+00:00",
    exact_commit_sha="1234567",
    browser_version="Chrome 150",
    os_version="Windows 11",
    scenario_labels=["factory-test"],
    release_gate_status="pass",
))
assert store.get(record.evaluation_id) is not None

from app.research import source_store as research
assert research.ResearchSourceStore.__name__ == "PostgresResearchSourceStore"
research_store = research.default_research_source_store()
item = SimpleNamespace(
    url="https://example.com/article?utm_source=test",
    title="PostgreSQL",
    content="PostgreSQL is authoritative.",
    metadata={"provider": "test"},
)
recorded = research_store.record_quick_search("PostgreSQL", "test", [item])
assert research_store.get_manifest(recorded.manifest.manifest_id) is not None

from app.image import asset_store as images
path = images.save_image_asset_bytes(
    b"not-a-real-png-but-stable",
    "image/png",
    "image:factory",
    {"purpose": "factory-test"},
)
assert path
assert "image:factory" in images.get_image_asset_manifest()["assets"]

from app.jobs import residency
assert residency.SQLiteModelResidencyStore.__name__ == "PostgresModelResidencyStore"
residency_store = residency.default_model_residency_store()
residency_store.upsert_record(residency.ModelResidencyRecord(
    model_id="model:factory",
    model_name="Factory",
    provider_id="provider:test",
    module="image",
    resource_class="gpu",
    status="loaded",
))
assert residency_store.list_records()[0].model_id == "model:factory"

from app.providers import cache_status
assert cache_status.SQLiteProviderModelRefreshStore.__name__ == "PostgresProviderModelRefreshStore"
refresh_store = cache_status.default_provider_model_refresh_store()
snapshot = refresh_store.record_snapshot(
    scope="all",
    reason="factory-test",
    provider_payload={"providers": [{"id": "provider:test"}], "models": []},
    cache_payload={"status": "ready", "diagnostics": []},
)
assert refresh_store.latest_snapshot().id == snapshot.id

from app.rpg.narrative import narrative_persistence
from app.rpg.narrative.narrative_event import NarrativeEvent
assert narrative_persistence.NarrativeEventStore.__name__ == "PostgresNarrativeEventStore"
narrative = narrative_persistence.NarrativeEventStore(session_id="campaign:factory")
narrative.save_events([
    NarrativeEvent(
        id="narrative:1",
        type="dialogue",
        description="Bran greets the player.",
        actors=["npc:bran"],
        location="The Rusty Flagon",
        importance=0.5,
        emotional_weight=0.1,
        tags=["greeting"],
        raw_event={"safe": True},
    )
])
assert narrative.get_session_events("campaign:factory")[0].id == "narrative:1"

from app.rpg.npc_evolution import profile_store
runtime_state = {
    "npc_evolution": {
        "arcs": {"npc:bran": {"arc_stage": "warming", "axes": {"trust": 1}}},
        "signals": [],
    }
}
persisted = profile_store.persist_npc_evolution_profiles(runtime_state=runtime_state)
assert persisted["ok"] is True
loaded = profile_store.load_npc_evolution_profiles_for_runtime(npc_ids=["npc:bran"])
assert loaded["loaded_count"] == 1

from app.chat import compaction, history_search
from app.chat.models import ChatMessage, ChatSession
from app.persistence.chat_compat import PostgresChatRepositoryAdapter
from app.chat.compaction import ConversationSummary

now = datetime.now(timezone.utc).isoformat()
PostgresChatRepositoryAdapter().save_sessions([
    ChatSession(
        id="chat:factory",
        title="Factory",
        provider_id=None,
        model_id=None,
        profile_id="profile:default",
        workspace_id="workspace:local",
        project_id=None,
        interaction_mode="system",
        transcript_policy="persistent",
        created_at=now,
        updated_at=now,
        messages=[
            ChatMessage(
                id="message:factory",
                role="user",
                content="PostgreSQL factory search term",
                created_at=now,
            )
        ],
    )
])
summary_repo = compaction.SQLiteConversationSummaryRepository()
summary = summary_repo.save(ConversationSummary(
    id="summary:factory",
    session_id="chat:factory",
    through_message_id="message:factory",
    source_message_count=1,
    summary="PostgreSQL summary",
    token_estimate=5,
    revision=1,
    created_at=now,
))
assert summary_repo.latest("chat:factory").id == summary.id
search = history_search.default_history_search_service().search(
    "PostgreSQL",
    profile_id="profile:default",
    workspace_id="workspace:local",
    project_id=None,
)
assert search.items and search.items[0].message_id == "message:factory"

import app.chat as chat_package
assert chat_package.default_chat_store().__class__.__name__ == "PostgresCharacterChatSessionStore"

from app.persistence.job_runtime_compat import PostgresJobStoreAdapter
assert getattr(PostgresJobStoreAdapter, "_omnix_inline_feature_jobs_installed", False) is True
assert getattr(PostgresJobStoreAdapter, "_omnix_rpg_turn_job_guard_installed", False) is True

from app.persistence.document_store import PostgresDocumentStore
records = PostgresDocumentStore().list(module="live-chat", record_type="evaluation-policy-store")
assert records
print("active-postgresql-feature-factories-ok")
'''


def test_active_feature_factories_use_postgresql(tmp_path: Path) -> None:
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
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        cwd=Path(__file__).resolve().parents[3],
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    assert "active-postgresql-feature-factories-ok" in result.stdout
