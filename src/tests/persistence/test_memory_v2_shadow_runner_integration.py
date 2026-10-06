"""The Memory v2 shadow runner imports v1, compares and evaluates readiness (WP-8.5)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.platform.assistant_memory.v2 import MemorySpaceKey
from app.platform.assistant_memory.v2.legacy_shadow import legacy_observation_id
from app.platform.assistant_memory.v2.shadow_report import build_shadow_report
from app.platform.assistant_memory.v2.shadow_runner import (
    MemoryV2ShadowRunner,
    ShadowRunnerError,
    run_shadow,
)
from app.persistence.migrations import apply_migrations
from app.persistence.tenant_scope import system_scope
from tests.persistence.test_memory_v2_authority_cutover_integration import (
    _database,
    _prepare_ready_space,
    _reset_global_authority_to_v1,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

PROFILE = "profile:alice"


@pytest.fixture
def database():
    database = _database()
    apply_migrations(database)
    _reset_global_authority_to_v1(database)
    owners: list[str] = []
    database.test_owners = owners  # type: ignore[attr-defined]
    try:
        yield database
    finally:
        with system_scope("operator.cli"), database.transaction() as connection:
            connection.execute("DELETE FROM omnix_memory_records WHERE owner_id = ANY(%s)", (owners,))
            connection.execute("DELETE FROM omnix_workspaces WHERE name = 'wp85 shadow runner test'")
        database.close()


def _owner(database) -> str:
    owner_id = f"sofia-{uuid4().hex}"
    database.test_owners.append(owner_id)
    return owner_id


def _workspace(database) -> str:
    with system_scope("operator.cli"), database.transaction() as connection:
        return str(connection.execute("SELECT id FROM omnix_workspaces ORDER BY id LIMIT 1").fetchone()[0])


def _insert(database, owner_id: str, content: str, *, scope: str = "global", scope_id: str = PROFILE,
            workspace_id: str | None = None, expires_at: datetime | None = None,
            sensitivity: str = "normal", trust_level: str = "user_approved") -> str:
    record_id = f"v1:{uuid4().hex}"
    with system_scope("operator.cli"), database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO omnix_memory_records (
                id, workspace_id, owner_type, owner_id, scope, scope_id, category, kind,
                content, normalized_content, source, trust_level, sensitivity,
                provenance_type, expires_at
            ) VALUES (%s, %s, 'character', %s, %s, %s, 'preference', 'preference',
                      %s, %s, 'user_saved', %s, %s, 'user_message', %s)
            """,
            (record_id, workspace_id or _workspace(database), owner_id, scope, scope_id,
             content, content.lower(), trust_level, sensitivity, expires_at),
        )
    return record_id


def _execute(database, sql: str, params: tuple) -> None:
    with system_scope("operator.cli"), database.transaction() as connection:
        connection.execute(sql, params)


def _run(database, *owner_ids: str, **options):
    options.setdefault("deadline_ms", 5_000.0)
    return run_shadow(database, owners={("character", owner_id) for owner_id in owner_ids}, **options)


def _space(database, owner_id: str, workspace_id: str | None = None) -> MemorySpaceKey:
    return MemorySpaceKey(
        principal_id=workspace_id or _workspace(database), owner_type="character", owner_id=owner_id,
    )


def _report_status(database, owner_id: str) -> str:
    report = build_shadow_report(database)
    return next(item.status for item in report.spaces if item.owner_id == owner_id)


def _observation_state(database, observation_id: str) -> tuple[str, dict]:
    with database.transaction() as connection:
        row = connection.execute(
            """
            SELECT COALESCE(d.state, 'active'), o.payload
              FROM omnix_memory_v2_observations o
              LEFT JOIN omnix_memory_v2_observation_dispositions d ON d.observation_id = o.observation_id
             WHERE o.observation_id = %s
            """,
            (observation_id,),
        ).fetchone()
    return str(row[0]), dict(row[1])


def _assertion_texts(database, space: MemorySpaceKey) -> set[str]:
    with database.transaction() as connection:
        rows = connection.execute(
            "SELECT object_value->>'literal' FROM omnix_memory_v2_graph_assertions "
            "WHERE principal_id = %s AND owner_type = %s AND owner_id = %s",
            (space.principal_id, space.owner_type, space.owner_id),
        ).fetchall()
    return {str(row[0]) for row in rows}


def test_an_imported_owner_becomes_ready_with_every_memory_found(database) -> None:
    owner = _owner(database)
    _insert(database, owner, "Skyrim is my favorite game")
    _insert(database, owner, "I take my coffee black with no sugar")
    _insert(database, owner, "We are planning the trip to Lisbon in May", scope="session", scope_id="session:trip")

    report = _run(database, owner)

    assert report.skipped_owners == []
    (outcome,) = report.spaces
    assert outcome.error is None
    assert (outcome.principal_id, outcome.imported, outcome.probes) == (_workspace(database), 3, 3)
    assert outcome.recall == 1.0 and outcome.precision == 1.0
    assert outcome.shadow_passed and outcome.graph_validation_passed and outcome.ready
    assert outcome.embeddings in {"synced", "model_absent"}
    assert report.all_ready
    assert _report_status(database, owner) == "ready"

    again = _run(database, owner)
    assert again.spaces[0].imported == 0 and again.spaces[0].ready


def test_secret_and_unapproved_records_are_imported_but_never_retrievable(database) -> None:
    owner = _owner(database)
    _insert(database, owner, "Skyrim is my favorite game")
    _insert(database, owner, "My bank PIN is on the yellow note", sensitivity="secret")
    _insert(database, owner, "The user might like jazz", trust_level="unverified_agent")
    space = _space(database, owner)

    (outcome,) = _run(database, owner).spaces

    assert outcome.imported == 3 and outcome.probes == 1
    assert outcome.ready and outcome.precision == 1.0
    assert _assertion_texts(database, space) == {"Skyrim is my favorite game"}


def test_forgotten_archived_and_revised_records_follow_v1(database) -> None:
    owner = _owner(database)
    forgotten = _insert(database, owner, "My locker code is on the blue card")
    archived = _insert(database, owner, "I used to live in Montreal")
    revised = _insert(database, owner, "My favorite tea is jasmine")
    _insert(database, owner, "Skyrim is my favorite game")
    space = _space(database, owner)
    assert _run(database, owner).spaces[0].ready

    _execute(database, "DELETE FROM omnix_memory_records WHERE id = %s", (forgotten,))
    _execute(database, "UPDATE omnix_memory_records SET status = 'archived', revision = 2 WHERE id = %s", (archived,))
    _execute(
        database,
        "UPDATE omnix_memory_records SET content = 'My favorite tea is oolong', "
        "normalized_content = 'my favorite tea is oolong', revision = 2 WHERE id = %s",
        (revised,),
    )
    assert _report_status(database, owner) == "v1_changed"

    (outcome,) = _run(database, owner).spaces
    assert (outcome.imported, outcome.revoked, outcome.purged) == (2, 2, 1)
    assert outcome.ready and outcome.recall == 1.0 and outcome.precision == 1.0
    assert _report_status(database, owner) == "ready"

    state, payload = _observation_state(database, legacy_observation_id(space, forgotten, 1))
    assert state == "purged" and "locker" not in str(payload)
    assert _observation_state(database, legacy_observation_id(space, archived, 1))[0] == "revoked"
    # The archived revision stays in v2 for management but is not retrievable.
    assert _observation_state(database, legacy_observation_id(space, archived, 2))[0] == "active"
    assert _observation_state(database, legacy_observation_id(space, revised, 1))[0] == "revoked"
    assert _observation_state(database, legacy_observation_id(space, revised, 2))[0] == "active"
    assert _assertion_texts(database, space) == {"My favorite tea is oolong", "Skyrim is my favorite game"}


def test_expired_records_are_not_retrievable_and_expiry_carries_over(database) -> None:
    owner = _owner(database)
    now = datetime.now(timezone.utc)
    _insert(database, owner, "The parking pass is valid this week", expires_at=now - timedelta(days=1))
    _insert(database, owner, "The guest wifi password changes monthly", expires_at=now + timedelta(days=30))
    space = _space(database, owner)

    (outcome,) = _run(database, owner).spaces

    assert outcome.imported == 2 and outcome.probes == 1 and outcome.ready
    with database.transaction() as connection:
        rows = connection.execute(
            "SELECT object_value->>'literal', valid_until FROM omnix_memory_v2_graph_assertions "
            "WHERE principal_id = %s AND owner_type = 'character' AND owner_id = %s",
            (space.principal_id, owner),
        ).fetchall()
    until = {str(row[0]): row[1] for row in rows}
    assert until["The parking pass is valid this week"] <= datetime.now(timezone.utc)
    assert abs((until["The guest wifi password changes monthly"] - (now + timedelta(days=30))).total_seconds()) < 5


def test_each_tenant_workspace_gets_its_own_space(database) -> None:
    owner = _owner(database)
    other = f"workspace:wp85-{uuid4().hex[:8]}"
    _execute(
        database,
        "INSERT INTO omnix_workspaces (id, name, created_by) "
        "SELECT %s, 'wp85 shadow runner test', created_by FROM omnix_workspaces ORDER BY id LIMIT 1",
        (other,),
    )
    _insert(database, owner, "Skyrim is my favorite game")
    _insert(database, owner, "I prefer window seats", workspace_id=other)

    report = _run(database, owner)

    assert report.skipped_owners == []
    assert sorted(item.principal_id for item in report.spaces) == sorted([_workspace(database), other])
    assert all(item.ready and item.imported == 1 for item in report.spaces)
    assert _assertion_texts(database, _space(database, owner, other)) == {"I prefer window seats"}


def test_an_owner_with_a_record_v1_cannot_read_is_skipped(database) -> None:
    owner = _owner(database)
    _insert(database, owner, "Skyrim is my favorite game")
    # Column defaults outside the v1 contract (trust 'normal', no provenance).
    _execute(
        database,
        "INSERT INTO omnix_memory_records (id, workspace_id, owner_type, owner_id, scope, scope_id, "
        "category, content, normalized_content, source) "
        "VALUES (%s, %s, 'character', %s, 'global', %s, 'preference', 'Raw row', 'raw row', 'user_saved')",
        (f"v1:{uuid4().hex}", _workspace(database), owner, PROFILE),
    )

    report = _run(database, owner)

    assert report.spaces == []
    assert report.skipped_owners == [{
        "owner_type": "character", "owner_id": owner,
        "reason": "invalid_v1_records", "invalid_record_count": 1,
    }]


def test_the_runner_refuses_once_v2_is_authoritative(database) -> None:
    authority, _space_key, receipt_id, _observation_id = _prepare_ready_space(database)
    authority.activate_v2((receipt_id,), activated_by="test:shadow-runner")
    try:
        with pytest.raises(ShadowRunnerError, match="v1 is authoritative"):
            MemoryV2ShadowRunner(database, owners=set()).run()
    finally:
        _reset_global_authority_to_v1(database)
