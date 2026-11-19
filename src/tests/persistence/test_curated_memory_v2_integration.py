"""Curated memory in Memory v2 (WP-8.5).

The memory service, policy and management code run on ``CuratedMemoryRepository``:
every record operation lands in the v2 observation log and becomes retrievable
(or stops being retrievable) at once. Memory v1 is retired: migration 0156 moves
an empty v1 installation to v2 and refuses one whose v1 still holds records.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.platform.assistant_memory.owner_service import OwnerAwareMemoryService
from app.platform.assistant_memory.persistence.owner_memory_store import PostgresOwnerAwareMemoryRepository
from app.platform.assistant_memory.scope import resolve_chat_scope
from app.platform.assistant_memory.v2 import MemorySpaceKey, RetrievalQuery, VisibilityScope
from app.platform.assistant_memory.v2.authority import PostgresMemoryV2AuthorityStore
from app.platform.assistant_memory.v2.curated_records import MemoryV2CuratedConvergence
from app.platform.assistant_memory.v2.memory_repository import CuratedMemoryRepository
from app.platform.assistant_memory.v2.runtime import PostgresMemoryV2Runtime
from app.conversation.memory_contracts import MemoryConflictError, MemoryRecord
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.persistence.tenant_scope import system_scope
from app.runtime.tenant_context import TenantContext, pop_tenant, push_tenant
from tests.support.database import admin_database_url

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

PROFILE = "profile:alice"
RETIREMENT_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "app/platform/assistant_memory/migrations/0156_memory_v1_retired.sql"
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=12, connect_timeout_seconds=10,
        statement_timeout_ms=60_000, lock_timeout_ms=30_000, application_name="omnix-curated-memory-v2-tests",
    ))


@pytest.fixture
def switched():
    """Memory v2 authoritative, a tenant installed, and the memory service on the curated repository."""
    database = _database()
    apply_migrations(database)
    assert PostgresMemoryV2AuthorityStore(database).current().epoch.authority == "v2"
    tenant = ensure_local_identity(database)
    token = push_tenant(tenant)
    legacy = PostgresOwnerAwareMemoryRepository(database)
    service = OwnerAwareMemoryService(CuratedMemoryRepository(legacy, database=database))
    try:
        yield database, tenant, service, legacy
    finally:
        pop_tenant(token)
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


def test_the_sweep_converges_a_write_whose_inline_convergence_failed(switched) -> None:
    database, tenant, _service, legacy = switched

    class _Broken:
        def run(self, **_options):
            raise RuntimeError("inline convergence unavailable")

    service = OwnerAwareMemoryService(
        CuratedMemoryRepository(legacy, database=database, convergence=_Broken()),
    )
    owner = f"sofia-{uuid4().hex}"
    _save(service, owner, "Skyrim is my favorite game")
    assert _retrieve(database, tenant, owner, "Which game do I like?") == []

    MemoryV2CuratedConvergence(database).run()

    assert _retrieve(database, tenant, owner, "Which game do I like?") == ["Skyrim is my favorite game"]


def _authority(connection) -> str:
    return str(connection.execute(
        "SELECT e.authority FROM omnix_memory_v2_authority_current c "
        "JOIN omnix_memory_v2_authority_epochs e ON e.epoch = c.current_epoch"
    ).fetchone()[0])


def _back_to_v1(connection) -> None:
    """Inside a transaction the test rolls back: a v1 epoch, as a database before 0156 had."""
    connection.execute(
        "INSERT INTO omnix_memory_v2_authority_epochs (epoch, authority, previous_epoch, activated_by, reason) "
        "SELECT MAX(epoch) + 1, 'v1', MAX(epoch), 'test:v1', 'before 0156' FROM omnix_memory_v2_authority_epochs"
    )
    connection.execute(
        "UPDATE omnix_memory_v2_authority_current "
        "SET current_epoch = (SELECT MAX(epoch) FROM omnix_memory_v2_authority_epochs)"
    )


def test_the_retirement_migration_moves_an_empty_v1_installation_to_v2(switched) -> None:
    sql = RETIREMENT_MIGRATION.read_text(encoding="utf-8")
    with psycopg.connect(admin_database_url()) as connection:
        connection.execute("SELECT set_config('omnix.system', 'on', true)")
        connection.execute("DELETE FROM omnix_memory_records")
        _back_to_v1(connection)
        assert _authority(connection) == "v1"
        connection.execute(sql)
        assert _authority(connection) == "v2"
        connection.rollback()


def test_the_retirement_migration_refuses_while_v1_holds_records(switched) -> None:
    _database_, tenant, _service, _legacy = switched
    sql = RETIREMENT_MIGRATION.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc)
    with psycopg.connect(admin_database_url()) as connection:
        connection.execute("SELECT set_config('omnix.system', 'on', true)")
        _back_to_v1(connection)
        connection.execute(
            "INSERT INTO omnix_memory_records (id, workspace_id, owner_type, owner_id, scope, scope_id, category, "
            "content, normalized_content, confidence, pinned, trust_level, sensitivity, provenance_type, source, "
            "status, revision, created_at, updated_at) VALUES (%s, %s, 'system', 'system-assistant', 'global', "
            "%s, 'fact', 'A v1 memory', 'a v1 memory', 1.0, FALSE, 'user_approved', 'normal', 'user_message', "
            "'user_saved', 'active', 1, %s, %s)",
            (f"memory:{uuid4().hex}", tenant.workspace_id, PROFILE, now, now),
        )
        with pytest.raises(psycopg.errors.RaiseException, match="still holds curated records"):
            connection.execute(sql)
        connection.rollback()


def _heard(service, owner_id: str, about: str, content: str) -> MemoryRecord:
    return service.create_heard_memory(
        _context(owner_id), about_character_id=about, kind="semantic_fact", category="fact", content=content,
        confidence=0.8, provenance_id="scene:chat:line",
    )


def _retrieve_present(database, tenant, owner_id: str, text: str, present, limit: int = 5) -> list[tuple]:
    result = PostgresMemoryV2Runtime(database).retrieve(RetrievalQuery(
        query_id=f"scene:{uuid4().hex}",
        space=MemorySpaceKey(principal_id=tenant.workspace_id, owner_type="character", owner_id=owner_id),
        visible_scopes=(VisibilityScope(kind="global", scope_id=PROFILE),),
        text=text, authority="final", as_of=datetime.now(timezone.utc), top_k=12, token_budget=4000,
        deadline_ms=5000, present_characters=present, per_character_limit=limit,
    ))
    return [(candidate.content, candidate.about_character_id) for candidate in result.candidates
            if candidate.prompt_eligible]


def test_a_heard_memory_is_about_the_character_and_retrieved_only_while_they_are_present(switched) -> None:
    database, tenant, service, _legacy = switched
    owner = f"character:mara-{uuid4().hex[:8]}"
    record = _heard(service, owner, "bea", "Bea is afraid of storms")
    _save(service, owner, "The user is afraid of storms")

    with database.transaction() as connection:
        subjects = connection.execute(
            "SELECT subject_entity_type, subject_entity_id FROM omnix_memory_v2_graph_assertions "
            "WHERE owner_id = %s AND status = 'active' ORDER BY subject_entity_type",
            (owner,),
        ).fetchall()
    assert [tuple(row) for row in subjects] == [("about_character", "bea"), ("profile", subjects[1][1])]

    assert ("Bea is afraid of storms", "bea") in _retrieve_present(database, tenant, owner, "storms", ("bea",))
    absent = _retrieve_present(database, tenant, owner, "storms", ("theo",))
    assert [content for content, _about in absent] == ["The user is afraid of storms"]
    unfiltered = _retrieve_present(database, tenant, owner, "storms", None)
    assert ("Bea is afraid of storms", "bea") in unfiltered
    assert record.about_character_id == "bea"


def test_the_owners_own_side_is_not_mistaken_for_a_memory_about_a_character(switched) -> None:
    # A conversation reading files the owner's stance, promises and jokes under the owner as a "character" subject.
    # Those stay the owner's, whoever is on the call; only an about-character memory waits for its character.
    database, tenant, service, _legacy = switched
    owner = f"character:mara-{uuid4().hex[:8]}"
    _save(service, owner, "Promised to show them the storm painting")
    with database.transaction() as connection:
        connection.execute(
            "UPDATE omnix_memory_v2_graph_assertions SET subject_entity_type = 'character' WHERE owner_id = %s",
            (owner,),
        )

    kept = _retrieve_present(database, tenant, owner, "storm painting", ("theo",))

    assert [content for content, about in kept] == ["Promised to show them the storm painting"]
    assert [about for _content, about in kept] == [None]


def test_the_newest_memories_per_present_character_are_retrieved(switched) -> None:
    database, tenant, service, _legacy = switched
    owner = f"character:mara-{uuid4().hex[:8]}"
    for content in ("Bea likes storms", "Bea likes thunder storms", "Bea likes summer storms"):
        _heard(service, owner, "bea", content)

    kept = _retrieve_present(database, tenant, owner, "storms", ("bea",), limit=2)

    assert sorted(content for content, _about in kept) == ["Bea likes summer storms", "Bea likes thunder storms"]


def test_an_open_loop_about_a_character_is_not_raised_as_the_persons(switched) -> None:
    from app.platform.assistant_memory.v2.understanding_view import read_open_loops

    database, tenant, service, _legacy = switched
    owner = f"character:mara-{uuid4().hex[:8]}"
    _save(service, owner, "Finish the storm painting", category="project")
    _heard(service, owner, "bea", "Bea wants to finish her boat")
    space = MemorySpaceKey(principal_id=tenant.workspace_id, owner_type="character", owner_id=owner)
    scopes = (VisibilityScope(kind="global", scope_id=PROFILE),)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE omnix_memory_v2_graph_assertions SET domain = 'open_loop' WHERE owner_id = %s", (owner,),
        )

    loops = read_open_loops(database, space, scopes, now=datetime.now(timezone.utc))

    assert [loop.text for loop in loops] == ["Finish the storm painting"]


def test_a_memory_about_a_character_never_reads_as_understanding_of_the_person(switched) -> None:
    # Defence in depth (6.6): even shaped as a reading's trait, an about-character row stays out of the person's.
    from app.platform.assistant_memory.v2.understanding import DERIVATION
    from app.platform.assistant_memory.v2.understanding_view import read_understanding

    database, tenant, service, _legacy = switched
    owner = f"character:mara-{uuid4().hex[:8]}"
    _save(service, owner, "Laughs at puns")
    _heard(service, owner, "bea", "Bea laughs at nothing")
    space = MemorySpaceKey(principal_id=tenant.workspace_id, owner_type="character", owner_id=owner)
    scopes = (VisibilityScope(kind="global", scope_id=PROFILE),)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE omnix_memory_v2_graph_assertions SET domain = 'trait', predicate = 'person_humor',"
            " derivation_version = %s WHERE owner_id = %s",
            (DERIVATION, owner),
        )

    items = read_understanding(database, space, scopes)

    assert [item.text for item in items if item.kind == "person"] == ["Laughs at puns"]
