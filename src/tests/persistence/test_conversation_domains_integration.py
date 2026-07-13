from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.errors import RevisionConflict
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=5,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-conversation-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_chat_messages, omnix_chat_sessions, "
            "omnix_memory_snapshot_items, omnix_memory_snapshots, "
            "omnix_memory_candidates, omnix_memory_events, omnix_memory_records, "
            "omnix_conversation_segments, omnix_character_versions, omnix_characters, "
            "omnix_asset_versions, omnix_assets, omnix_settings, omnix_secret_references, "
            "omnix_audit_events, omnix_idempotency_keys, omnix_workspace_memberships, "
            "omnix_workspaces, omnix_users CASCADE"
        )


def test_character_versions_are_immutable_and_tenant_scoped() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            created = work.characters.create(
                context,
                character_id="character:maya",
                profile={"display_name": "Maya", "description": "Warm and perceptive"},
            )
            work.commit()
        assert created["active_version"] == 1

        with unit_of_work(database) as work:
            updated = work.characters.update(
                context,
                character_id="character:maya",
                profile={"display_name": "Maya", "description": "Warm, perceptive, concise"},
                expected_version=1,
            )
            versions = work.characters.versions(context, "character:maya")
            work.commit()
        assert updated["active_version"] == 2
        assert [item["version"] for item in versions] == [2, 1]
        assert versions[1]["profile"]["description"] == "Warm and perceptive"

        with unit_of_work(database) as work:
            with pytest.raises(RevisionConflict):
                work.characters.update(
                    context,
                    character_id="character:maya",
                    profile={"display_name": "Maya"},
                    expected_version=1,
                )
            work.rollback()

        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO omnix_users (id, display_name) VALUES ('user:other', 'Other')"
            )
            connection.execute(
                "INSERT INTO omnix_workspaces (id, name, created_by) "
                "VALUES ('workspace:other', 'Other', 'user:other')"
            )
            connection.execute(
                "INSERT INTO omnix_workspace_memberships "
                "(id, workspace_id, user_id, roles) "
                "VALUES ('membership:other', 'workspace:other', 'user:other', ARRAY['owner'])"
            )
        with unit_of_work(database) as work:
            other = work.identities.load_context(
                user_id="user:other", workspace_id="workspace:other"
            )
            assert work.characters.get_character(other, "character:maya") is None
            work.rollback()
    finally:
        database.close()


def test_memory_revision_candidate_and_snapshot_lifecycle() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            first = work.memories.create(
                context,
                {
                    "id": "memory:1",
                    "owner_type": "user",
                    "owner_id": context.user_id,
                    "category": "preference",
                    "content": "Prefers concise summaries",
                    "source": "user",
                },
            )
            second = work.memories.create(
                context,
                {
                    "id": "memory:2",
                    "owner_type": "user",
                    "owner_id": context.user_id,
                    "category": "project",
                    "content": "Omnix uses PostgreSQL",
                    "source": "approved",
                    "pinned": True,
                },
            )
            candidate = work.memories.create_candidate(
                context,
                {
                    "id": "candidate:1",
                    "source_message_id": "message:source",
                    "candidate_fingerprint": "fingerprint:1",
                    "proposed_owner_type": "user",
                    "proposed_owner_id": context.user_id,
                    "proposed_category": "preference",
                    "proposed_content": "Uses local models",
                },
            )
            replay = work.memories.create_candidate(
                context,
                {
                    "id": "candidate:duplicate",
                    "source_message_id": "message:source",
                    "candidate_fingerprint": "fingerprint:1",
                    "proposed_owner_type": "user",
                    "proposed_owner_id": context.user_id,
                    "proposed_category": "preference",
                    "proposed_content": "Uses local models",
                },
            )
            updated = work.memories.update(
                context,
                memory_id=first["id"],
                expected_revision=1,
                changes={"pinned": True, "content": "Prefers concise, complete summaries"},
            )
            snapshot = work.memories.create_snapshot(
                context,
                snapshot_id="snapshot:1",
                owner_type="user",
                owner_id=context.user_id,
                record_ids=[second["id"], updated["id"]],
            )
            records = work.memories.list_records(
                context,
                owner_type="user",
                owner_id=context.user_id,
            )
            work.commit()

        assert candidate["id"] == replay["id"] == "candidate:1"
        assert updated["revision"] == 2
        assert snapshot["revision"] == 1
        assert [item["position"] for item in snapshot["items"]] == [0, 1]
        assert {record["id"] for record in records} == {"memory:1", "memory:2"}
        with database.connection() as connection:
            event_types = {
                str(row[0])
                for row in connection.execute(
                    "SELECT event_type FROM omnix_memory_events"
                ).fetchall()
            }
        assert {"memory.created", "memory.updated", "memory.snapshot_created"}.issubset(
            event_types
        )
    finally:
        database.close()


def test_chat_messages_append_incrementally_with_cursor_pagination() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            session = work.chats.create_session(
                context,
                {
                    "id": "chat:1",
                    "title": "PostgreSQL migration",
                    "provider_id": "lmstudio",
                    "model_id": "local-model",
                },
            )
            first = work.chats.append_message(
                context,
                session["id"],
                {"id": "message:1", "role": "user", "content": "Hello"},
            )
            second = work.chats.append_message(
                context,
                session["id"],
                {
                    "id": "message:2",
                    "role": "assistant",
                    "content": "Hello from PostgreSQL",
                    "metadata": {"delivery_status": "complete"},
                },
            )
            work.commit()
        assert (first["position"], second["position"]) == (0, 1)

        with unit_of_work(database) as work:
            page_one = work.chats.list_messages(context, "chat:1", limit=1)
            page_two = work.chats.list_messages(
                context, "chat:1", limit=10, after_position=page_one[-1]["position"]
            )
            stored = work.chats.get_session(context, "chat:1")
            work.rollback()
        assert [item["id"] for item in page_one] == ["message:1"]
        assert [item["id"] for item in page_two] == ["message:2"]
        assert stored is not None
        assert stored["message_count"] == 2
        assert stored["revision"] == 3

        with unit_of_work(database) as work:
            changed = work.chats.update_session(
                context,
                session_id="chat:1",
                expected_revision=3,
                title="Centralized persistence",
                settings={"memory_enabled": True},
            )
            work.commit()
        assert changed["revision"] == 4
        with unit_of_work(database) as work:
            with pytest.raises(RevisionConflict):
                work.chats.update_session(
                    context,
                    session_id="chat:1",
                    expected_revision=3,
                    title="Stale",
                )
            work.rollback()
    finally:
        database.close()


def test_conversation_domain_changes_rollback_together() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with pytest.raises(RuntimeError, match="abort domain transaction"):
            with unit_of_work(database) as work:
                work.characters.create(
                    context,
                    character_id="character:rollback",
                    profile={"display_name": "Rollback"},
                )
                work.chats.create_session(
                    context,
                    {"id": "chat:rollback", "title": "Rollback"},
                )
                raise RuntimeError("abort domain transaction")
        with unit_of_work(database) as work:
            assert work.characters.get_character(context, "character:rollback") is None
            assert work.chats.get_session(context, "chat:rollback") is None
            work.rollback()
    finally:
        database.close()
