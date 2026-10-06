"""Curated memory after the switch to Memory v2 (WP-8.5).

v1's own service, policy and management code runs on the authority-routed
repository; with v2 authoritative every record operation lands in the v2
observation log and becomes retrievable (or stops being retrievable) at once.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.platform.assistant_memory.owner_service import OwnerAwareMemoryService
from app.platform.assistant_memory.persistence.owner_memory_store import PostgresOwnerAwareMemoryRepository
from app.platform.assistant_memory.scope import resolve_chat_scope
from app.platform.assistant_memory.service import LegacyMemoryReadOnlyError
from app.platform.assistant_memory.v2 import MemorySpaceKey, RetrievalQuery, VisibilityScope
from app.platform.assistant_memory.v2.authority import CutoverNotReadyError, PostgresMemoryV2AuthorityStore
from app.platform.assistant_memory.v2.curated_records import MemoryV2CuratedConvergence
from app.platform.assistant_memory.v2.memory_repository import MemoryAuthorityRoutedRepository
from app.platform.assistant_memory.v2.runtime import PostgresMemoryV2Runtime, UnsafeMemoryRollbackError
from app.platform.assistant_memory.v2.shadow_runner import run_shadow
from app.conversation.memory_contracts import MemoryConflictError, MemoryRecord
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.persistence.tenant_scope import system_scope
from app.runtime.tenant_context import TenantContext, pop_tenant, push_tenant
from tests.persistence.test_memory_v2_authority_cutover_integration import (
    _database,
    _reset_global_authority_to_v1,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

PROFILE = "profile:alice"


@pytest.fixture
def switched():
    """v2 authoritative with no v1 memory, a tenant installed, and v1's service on the routed repository."""
    database = _database()
    apply_migrations(database)
    _reset_global_authority_to_v1(database)
    tenant = ensure_local_identity(database)
    token = push_tenant(tenant)
    authority = PostgresMemoryV2AuthorityStore(database)
    authority.activate_v2((), activated_by="test:switch", reason="empty v1")
    legacy = PostgresOwnerAwareMemoryRepository(database)
    service = OwnerAwareMemoryService(MemoryAuthorityRoutedRepository(legacy, database=database))
    try:
        yield database, tenant, service, legacy
    finally:
        pop_tenant(token)
        _reset_global_authority_to_v1(database)
        database.close()


def _context(owner_id: str, session_id: str = "session:switch"):
    return resolve_chat_scope(session_id, profile_id=PROFILE, owner_type="character", owner_id=owner_id)


def _retrieve(database, tenant, owner_id: str, text: str) -> list[str]:
    result = PostgresMemoryV2Runtime(database).retrieve(RetrievalQuery(
        query_id=f"switch:{uuid4().hex}",
        space=MemorySpaceKey(principal_id=tenant.workspace_id, owner_type="character", owner_id=owner_id),
        visible_scopes=(
            VisibilityScope(kind="global", scope_id=PROFILE),
            VisibilityScope(kind="session", scope_id="session:switch"),
        ),
        text=text,
        authority="final",
        as_of=datetime.now(timezone.utc),
        top_k=12,
        token_budget=4000,
        deadline_ms=5000,
    ))
    return [candidate.content for candidate in result.candidates]


def _save(service, owner_id: str, content: str, **options) -> MemoryRecord:
    return service.create_explicit_memory(
        _context(owner_id), scope=options.pop("scope", "global"), category=options.pop("category", "preference"),
        content=content, provenance_id="message:switch", **options,
    )


def test_a_saved_memory_is_listed_and_retrievable_at_once(switched) -> None:
    database, tenant, service, _legacy = switched
    owner = f"sofia-{uuid4().hex}"

    record = _save(service, owner, "Skyrim is my favorite game")

    assert [item.id for item in service.list_active(_context(owner))] == [record.id]
    assert service.repository.get_record(record.id) == record
    # The memory text itself, not "<principal> <predicate> <text>".
    assert _retrieve(database, tenant, owner, "Which game do I like?") == ["Skyrim is my favorite game"]


def test_edit_pin_move_and_archive_keep_one_current_revision(switched) -> None:
    database, tenant, service, _legacy = switched
    owner = f"sofia-{uuid4().hex}"
    context = _context(owner)
    record = _save(service, owner, "My favorite tea is jasmine")

    edited = service.edit_memory(context, record.id, content="My favorite tea is oolong", expected_revision=1)
    pinned = service.set_pinned(context, record.id, pinned=True, expected_revision=2)
    moved = service.move_memory(context, record.id, target_scope="session", expected_revision=3)

    assert (edited.revision, pinned.revision, moved.revision) == (2, 3, 4)
    assert [(item.content, item.pinned, item.scope) for item in service.list_active(context)] == [
        ("My favorite tea is oolong", True, "session"),
    ]
    assert _retrieve(database, tenant, owner, "Which tea do I like?") == ["My favorite tea is oolong"]
    with pytest.raises(MemoryConflictError, match="revision conflict"):
        service.edit_memory(context, record.id, content="stale write", expected_revision=2)

    archived = service.repository.update_record(
        moved.model_copy(update={"status": "archived", "pinned": False}), expected_revision=4,
    )
    assert archived.status == "archived"
    assert service.list_active(context) == []
    assert [item.id for item in service.repository.list_records(owner_type="character", owner_id=owner,
                                                                scope="session", scope_id="session:switch",
                                                                status="archived")] == [record.id]
    assert _retrieve(database, tenant, owner, "Which tea do I like?") == []


def test_forget_purges_every_revision_and_snapshot_text(switched) -> None:
    database, tenant, service, legacy = switched
    owner = f"sofia-{uuid4().hex}"
    context = _context(owner)
    record = _save(service, owner, "My locker code is on the blue card")
    service.edit_memory(context, record.id, content="My locker code is on the green card", expected_revision=1)
    snapshot = service.create_session_snapshot(context, token_budget=4000)
    assert [item.memory_record_id for item in snapshot.items] == [record.id]

    assert service.forget_memory(context, record.id, expected_revision=2) is True

    assert service.list_active(context) == []
    assert service.repository.get_record(record.id) is None
    assert _retrieve(database, tenant, owner, "Where is my locker code?") == []
    assert legacy.get_snapshot(snapshot.id).items == []
    with database.transaction() as connection:
        texts = connection.execute(
            "SELECT payload::text FROM omnix_memory_v2_observations "
            "WHERE principal_id = %s AND owner_id = %s",
            (tenant.workspace_id, owner),
        ).fetchall()
    assert texts and not any("locker" in str(row[0]) for row in texts)


def test_approving_a_suggestion_writes_v2_once(switched) -> None:
    database, tenant, service, legacy = switched
    owner = f"sofia-{uuid4().hex}"
    context = _context(owner)
    candidate = service.propose_memory(
        context, source_session_id="session:switch", source_message_id=f"message:{uuid4().hex}",
        scope="global", category="preference", content="The user enjoys jazz", confidence=0.8,
    )

    record = service.approve_candidate(context, candidate.id)

    assert legacy.get_candidate(candidate.id).status == "accepted"
    assert [item.id for item in service.list_active(context)] == [record.id]
    assert record.trust_level == "user_approved"
    assert _retrieve(database, tenant, owner, "What music do I enjoy?") == ["The user enjoys jazz"]
    # A retried approval returns the same record instead of a second memory.
    again = service.repository.accept_candidate(candidate.id, record, resolved_at=record.created_at)
    assert again.id == record.id
    assert len(service.list_active(context)) == 1


def test_owner_reset_purges_v2_memory(switched) -> None:
    database, tenant, service, _legacy = switched
    owner = f"sofia-{uuid4().hex}"
    _save(service, owner, "Skyrim is my favorite game")
    _save(service, owner, "I take my coffee black")

    records, _candidates, _snapshots = service.repository.delete_owner(owner_type="character", owner_id=owner)

    assert records == 2
    assert service.list_active(_context(owner)) == []
    assert _retrieve(database, tenant, owner, "coffee game") == []


def test_v2_memory_stays_inside_its_tenant(switched) -> None:
    database, tenant, service, _legacy = switched
    owner = f"sofia-{uuid4().hex}"
    record = _save(service, owner, "Skyrim is my favorite game")
    other = f"workspace:switch-{uuid4().hex[:8]}"
    with system_scope("operator.cli"), database.transaction() as connection:
        connection.execute(
            "INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, 'wp85 switch test', %s)",
            (other, tenant.user_id),
        )
    token = push_tenant(TenantContext(user_id=tenant.user_id, workspace_id=other, membership_id="m",
                                      roles=frozenset({"owner"})))
    try:
        assert service.repository.get_record(record.id) is None
        assert service.list_active(_context(owner)) == []
    finally:
        pop_tenant(token)
        with system_scope("operator.cli"), database.transaction() as connection:
            connection.execute("DELETE FROM omnix_workspaces WHERE id = %s", (other,))


def test_v1_record_writes_are_refused_inside_their_transaction(switched) -> None:
    _database_, _tenant, _service, legacy = switched
    record = MemoryRecord(
        id=f"memory:{uuid4().hex}", owner_type="character", owner_id="sofia", scope="global",
        scope_id=PROFILE, category="fact", source="user_saved", content="Written to v1 after the switch",
        normalized_content="written to v1 after the switch", provenance_type="user_message",
        created_at=datetime.now(timezone.utc).isoformat(), updated_at=datetime.now(timezone.utc).isoformat(),
    )
    with pytest.raises(LegacyMemoryReadOnlyError, match="read-only"):
        legacy.create_record(record)


def test_rollback_is_refused_once_memory_was_written_under_v2(switched) -> None:
    database, _tenant, service, _legacy = switched
    _save(service, f"sofia-{uuid4().hex}", "Skyrim is my favorite game")

    with pytest.raises(UnsafeMemoryRollbackError, match="discard or resurrect"):
        PostgresMemoryV2Runtime(database).rollback_to_v1(activated_by="test:switch", reason="undo")


def test_an_empty_switch_can_be_rolled_back_until_something_is_written() -> None:
    database = _database()
    try:
        apply_migrations(database)
        _reset_global_authority_to_v1(database)
        PostgresMemoryV2AuthorityStore(database).activate_v2((), activated_by="test:switch", reason="empty v1")
        state = PostgresMemoryV2Runtime(database).rollback_to_v1(activated_by="test:switch", reason="undo")
        assert state.epoch.authority == "v1"
    finally:
        _reset_global_authority_to_v1(database)
        database.close()


def test_the_sweep_converges_a_write_whose_inline_convergence_failed(switched) -> None:
    database, tenant, _service, legacy = switched

    class _Broken:
        def run(self, **_options):
            raise RuntimeError("inline convergence unavailable")

    service = OwnerAwareMemoryService(
        MemoryAuthorityRoutedRepository(legacy, database=database, convergence=_Broken()),
    )
    owner = f"sofia-{uuid4().hex}"
    _save(service, owner, "Skyrim is my favorite game")
    assert _retrieve(database, tenant, owner, "Which game do I like?") == []

    MemoryV2CuratedConvergence(database).run()

    assert _retrieve(database, tenant, owner, "Which game do I like?") == ["Skyrim is my favorite game"]


def _v1_record(database, owner_id: str, content: str) -> None:
    # The local tenant's workspace: the one the switched service serves.
    workspace_id = ensure_local_identity(database).workspace_id
    with system_scope("operator.cli"), database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO omnix_memory_records (
                id, workspace_id, owner_type, owner_id, scope, scope_id, category, kind,
                content, normalized_content, source, trust_level, provenance_type
            ) VALUES (%s, %s, 'character', %s, 'global', %s, 'preference', 'preference',
                      %s, %s, 'user_saved', 'user_approved', 'user_message')
            """,
            (f"v1:{uuid4().hex}", workspace_id, owner_id, PROFILE, content, content.lower()),
        )


def test_activation_refuses_v1_changes_made_after_the_shadow_run() -> None:
    database = _database()
    owner = f"sofia-{uuid4().hex}"
    try:
        apply_migrations(database)
        _reset_global_authority_to_v1(database)
        _v1_record(database, owner, "Skyrim is my favorite game")
        report = run_shadow(database, owners={("character", owner)}, deadline_ms=5000)
        assert report.all_ready
        receipts = tuple(item.receipt_id for item in report.spaces)
        _v1_record(database, owner, "Saved after the shadow run")

        with pytest.raises(CutoverNotReadyError, match="changed since the shadow run"):
            PostgresMemoryV2AuthorityStore(database).activate_v2(receipts, activated_by="test:switch")
        with pytest.raises(CutoverNotReadyError):
            PostgresMemoryV2AuthorityStore(database).activate_v2((), activated_by="test:switch")
        assert PostgresMemoryV2AuthorityStore(database).current().epoch.authority == "v1"

        report = run_shadow(database, owners={("character", owner)}, deadline_ms=5000)
        state = PostgresMemoryV2AuthorityStore(database).activate_v2(
            tuple(item.receipt_id for item in report.spaces), activated_by="test:switch",
        )
        assert state.epoch.authority == "v2"
        # Imported v1 memories are managed and served as curated memory now.
        tenant = ensure_local_identity(database)
        token = push_tenant(tenant)
        try:
            service = OwnerAwareMemoryService(
                MemoryAuthorityRoutedRepository(PostgresOwnerAwareMemoryRepository(database), database=database),
            )
            context = _context(owner)
            imported = sorted(service.list_active(context), key=lambda item: item.content)
            assert [item.content for item in imported] == ["Saved after the shadow run", "Skyrim is my favorite game"]
            edited = service.edit_memory(context, imported[1].id, content="Morrowind is my favorite game",
                                         expected_revision=imported[1].revision)
            assert edited.revision == imported[1].revision + 1
            assert _retrieve(database, tenant, owner, "favorite game") == ["Morrowind is my favorite game"]
        finally:
            pop_tenant(token)
    finally:
        _reset_global_authority_to_v1(database)
        database.close()
