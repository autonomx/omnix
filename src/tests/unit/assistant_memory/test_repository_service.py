from __future__ import annotations

import sqlite3

import pytest

from app.assistant_memory import (
    MemoryConflictError,
    MemoryPolicyError,
    MemoryService,
    SQLiteMemoryRepository,
    resolve_chat_scope,
)


def service_at(path) -> MemoryService:
    return MemoryService(SQLiteMemoryRepository(path))


def test_repository_is_restart_safe_and_enforces_optimistic_revisions(tmp_path):
    path = tmp_path / "memory.sqlite3"
    context = resolve_chat_scope("chat:one", project_id="project:omnix")
    service = service_at(path)
    created = service.create_explicit_memory(
        context,
        scope="project",
        category="instruction",
        content="Use the rpg branch.",
        provenance_id="msg:one",
    )

    restarted = service_at(path)
    stored = restarted.repository.get_record(created.id)
    assert stored is not None
    assert stored.content == "Use the rpg branch."

    updated = restarted.edit_memory(
        context,
        created.id,
        content="Use the rpg branch as source of truth.",
        expected_revision=1,
    )
    assert updated.revision == 2
    with pytest.raises(MemoryConflictError):
        restarted.edit_memory(
            context,
            created.id,
            content="Stale update",
            expected_revision=1,
        )


def test_candidate_creation_is_idempotent_and_approval_is_atomic(tmp_path):
    service = service_at(tmp_path / "memory.sqlite3")
    context = resolve_chat_scope("chat:one", project_id="project:omnix")

    first = service.propose_memory(
        context,
        source_session_id="chat:one",
        source_message_id="msg:one",
        scope="project",
        category="preference",
        content="Prefer narrow pull requests.",
        confidence=0.9,
    )
    second = service.propose_memory(
        context,
        source_session_id="chat:one",
        source_message_id="msg:one",
        scope="project",
        category="preference",
        content="Prefer narrow pull requests.",
        confidence=0.9,
    )

    assert second.id == first.id
    approved = service.approve_candidate(context, first.id, pinned=True)
    assert approved.trust_level == "user_approved"
    assert approved.pinned is True
    assert service.repository.get_candidate(first.id).status == "accepted"
    with pytest.raises(MemoryPolicyError):
        service.approve_candidate(context, first.id)


def test_selection_filters_scope_and_prioritizes_pinned_records(tmp_path):
    service = service_at(tmp_path / "memory.sqlite3")
    context = resolve_chat_scope("chat:one", project_id="project:omnix")
    other = resolve_chat_scope("chat:two", project_id="project:other")

    global_record = service.create_explicit_memory(
        context,
        scope="global",
        category="preference",
        content="Prefer detailed answers.",
        provenance_id="msg:global",
        pinned=True,
    )
    project_record = service.create_explicit_memory(
        context,
        scope="project",
        category="instruction",
        content="Use GitHub Actions as verification truth.",
        provenance_id="msg:project",
    )
    service.create_explicit_memory(
        other,
        scope="project",
        category="fact",
        content="This belongs to another project.",
        provenance_id="msg:other",
    )

    selection = service.resolve_active_memory(context, token_budget=1_000)
    assert [record.id for record in selection.records] == [global_record.id, project_record.id]
    assert selection.diagnostics.candidate_count == 2

    bounded = service.resolve_active_memory(context, token_budget=8)
    assert [record.id for record in bounded.records] == [global_record.id]
    assert bounded.diagnostics.truncated is True


def test_forget_purges_record_from_existing_snapshot_items(tmp_path):
    service = service_at(tmp_path / "memory.sqlite3")
    context = resolve_chat_scope("chat:one", project_id="project:omnix")
    forgotten = service.create_explicit_memory(
        context,
        scope="project",
        category="fact",
        content="Sensitive old project fact.",
        provenance_id="msg:one",
    )
    retained = service.create_explicit_memory(
        context,
        scope="project",
        category="instruction",
        content="Retained project instruction.",
        provenance_id="msg:two",
    )
    snapshot = service.create_session_snapshot(context, token_budget=1_000)
    assert {item.memory_record_id for item in snapshot.items} == {forgotten.id, retained.id}

    assert service.forget_memory(context, forgotten.id, expected_revision=1) is True
    restored = service.repository.get_snapshot(snapshot.id)
    assert restored is not None
    assert [item.memory_record_id for item in restored.items] == [retained.id]
    assert service.repository.get_record(forgotten.id) is None

    events = service.repository.list_events(entity_id=forgotten.id)
    forgotten_event = [event for event in events if event["event_type"] == "memory.forgotten"][0]
    assert forgotten_event["metadata"] == {"forgotten_revision": 1}
    assert "Sensitive old project fact" not in str(forgotten_event)


def test_candidate_cannot_be_approved_from_an_unrelated_scope(tmp_path):
    service = service_at(tmp_path / "memory.sqlite3")
    source_context = resolve_chat_scope("chat:one", project_id="project:omnix")
    wrong_context = resolve_chat_scope("chat:two", project_id="project:other")
    candidate = service.propose_memory(
        source_context,
        source_session_id="chat:one",
        source_message_id="msg:one",
        scope="project",
        category="fact",
        content="Project-local fact.",
        confidence=0.8,
    )

    with pytest.raises(MemoryPolicyError, match="candidate_scope_mismatch"):
        service.approve_candidate(wrong_context, candidate.id)
    assert service.repository.get_candidate(candidate.id).status == "pending"


def test_schema_initialization_is_idempotent(tmp_path):
    path = tmp_path / "memory.sqlite3"
    SQLiteMemoryRepository(path)
    SQLiteMemoryRepository(path)

    with sqlite3.connect(path) as connection:
        version = connection.execute(
            "SELECT version FROM memory_schema_version LIMIT 1"
        ).fetchone()[0]
    assert version == 1
