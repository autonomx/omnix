"""Audiobook routes act as the account of each request, not the first one served (ST-P.1)."""
from __future__ import annotations

import os
import uuid

import pytest

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="PostgreSQL integration tests need OMNIX_TEST_DATABASE_URL",
    ),
]


@pytest.fixture
def two_accounts():
    """Two workspaces with their tenants, on the scratch database."""
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.identity_service import PostgresIdentityRepository, ensure_local_identity
    from app.persistence.job_store import PostgresJobStoreAdapter
    from app.persistence.tenant_scope import system_scope

    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_max=4))
    ensure_local_identity(database)
    user_id = PostgresJobStoreAdapter(database).context.user_id
    workspaces = [f"workspace:audiobook-{name}-{uuid.uuid4().hex[:10]}" for name in ("a", "b")]
    contexts = []
    with system_scope("identity.provision"), database.transaction() as connection:
        for workspace_id in workspaces:
            connection.execute("INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, %s, %s)",
                               (workspace_id, workspace_id, user_id))
            connection.execute(
                "INSERT INTO omnix_workspace_memberships (id, workspace_id, user_id, roles) VALUES (%s, %s, %s, %s)",
                (f"membership:{uuid.uuid4().hex}", workspace_id, user_id, ["owner", "admin", "member"]),
            )
            contexts.append(PostgresIdentityRepository(connection).load_context(
                user_id=user_id, workspace_id=workspace_id))
    try:
        yield database, contexts[0], contexts[1]
    finally:
        with system_scope("identity.provision"), database.transaction() as connection:
            _clear_audiobook_rows(connection, workspaces)
            connection.execute("DELETE FROM omnix_workspaces WHERE id = ANY(%s)", (workspaces,))
        database.close()


def _clear_audiobook_rows(connection, workspaces):
    """Audiobook rows neither cascade from their workspace nor change once written: clear them, triggers off."""
    connection.execute("SET LOCAL session_replication_role = replica")
    tables = [row[0] for row in connection.execute(
        "SELECT table_name FROM information_schema.columns"
        " WHERE column_name = 'workspace_id' AND table_name LIKE 'omnix_audiobook%%'")]
    for table in tables:
        connection.execute(f"DELETE FROM {table} WHERE workspace_id = ANY(%s)", (workspaces,))
    connection.execute("SET LOCAL session_replication_role = DEFAULT")


def test_each_request_sees_only_its_own_accounts_projects(two_accounts, monkeypatch):
    from app.apps.audiobook import routes
    from app.runtime.tenant_context import pop_tenant, push_tenant

    database, account_a, account_b = two_accounts
    monkeypatch.setattr(routes, "default_database", lambda: database)
    monkeypatch.setattr(routes, "default_blob_store", lambda: None)
    monkeypatch.setattr(routes, "_SERVICE", None)

    def as_account(context, call):
        token = push_tenant(context)
        try:
            return call()
        finally:
            pop_tenant(token)

    def titles():
        return {project["title"] for project in routes.list_projects(offset=0)["projects"]}

    # A serves the first request, the one the routes used to keep.
    as_account(account_a, lambda: routes._service_and_context()[0].create_project(
        routes._service_and_context()[1], title="A's book"))
    assert as_account(account_a, titles) == {"A's book"}

    assert as_account(account_b, titles) == set()
    as_account(account_b, lambda: routes._service_and_context()[0].create_project(
        routes._service_and_context()[1], title="B's book"))
    assert as_account(account_b, titles) == {"B's book"}
    assert as_account(account_a, titles) == {"A's book"}


STORY = {
    "title": "The Tide",
    "story_project_id": "story-tide",
    "story_version_id": "version-3",
    "chapters": [
        {"title": "The Harbour", "blocks": [
            {"text": "Dusk fell over the harbour."},
            {"kind": "dialogue", "text": "“Hold fast.”", "speaker": "Mara"},
            {"kind": "dialogue", "text": "“Aye, captain.”", "speaker": "Tomas"},
        ]},
        {"title": "The Stranger", "blocks": [
            {"text": "A boat came out of the fog."},
            {"kind": "dialogue", "text": "“Who are you?”", "speaker": "Stranger", "unverified": True},
            {"kind": "dialogue", "text": "“Stay back.”", "speaker": "the captain"},
        ]},
    ],
    "cast": [{"name": "Mara", "aliases": ["the captain"]}, {"name": "Tomas"}],
}


def test_a_story_becomes_a_book_with_its_speakers_given(two_accounts, monkeypatch, tmp_path):
    """ST-4.4: the cast are the speakers, and analysis attributes the story's lines without a model."""
    from app.apps.audiobook import routes, worker
    from app.apps.audiobook.annotation import narrator_id
    from app.apps.audiobook.story_import import StoryImport
    from app.persistence.blob_store import LocalBlobStore
    from app.runtime.tenant_context import pop_tenant, push_tenant

    database, account_a, account_b = two_accounts
    blobs = LocalBlobStore(tmp_path)
    monkeypatch.setattr(routes, "default_database", lambda: database)
    monkeypatch.setattr(routes, "default_blob_store", lambda: blobs)
    monkeypatch.setattr(routes, "_SERVICE", None)
    monkeypatch.setattr(worker, "local_classifier", lambda: None)
    monkeypatch.setattr(worker, "local_structure_classifier", lambda: None)

    def as_account(context, call):
        token = push_tenant(context)
        try:
            return call()
        finally:
            pop_tenant(token)

    created = as_account(account_a, lambda: routes.import_story(StoryImport.model_validate(STORY)))
    project_id = str(created["id"])
    assert as_account(account_b, lambda: routes.list_projects(offset=0))["projects"] == []

    assert worker.run_ingest_once(database, blobs, account_a, worker_id="test")
    service = routes._audiobook_service()
    service.reclassify_source(account_a, project_id=project_id)
    assert worker.run_analyze_once(database, account_a, worker_id="test")
    # B's worker finds nothing of A's to do.
    assert not worker.run_analyze_once(database, account_b, worker_id="test")

    with database.transaction() as connection:
        connection.execute("SELECT set_config('omnix.workspace_id', %s, true)", (account_a.workspace_id,))
        speakers = dict(connection.execute(
            "SELECT canonical_name, id::text FROM omnix_audiobook_speakers WHERE project_id = %s AND status = 'active'",
            (project_id,),
        ).fetchall())
        aliases = connection.execute(
            "SELECT alias, status FROM omnix_audiobook_speaker_aliases WHERE project_id = %s", (project_id,),
        ).fetchall()
        lines = connection.execute(
            """SELECT story_project_id, story_version_id, jsonb_array_length(speaker_lines)
                 FROM omnix_audiobook_story_sources WHERE project_id = %s""", (project_id,),
        ).fetchall()
        spoken = connection.execute(
            """SELECT s.source_text, a.speaker_id::text, a.review_status, a.evidence->>'speaker_source'
                 FROM omnix_audiobook_spans s
                 JOIN omnix_audiobook_chapters c ON c.workspace_id = s.workspace_id AND c.id = s.chapter_id
                 JOIN omnix_audiobook_annotations a ON a.workspace_id = s.workspace_id AND a.span_id = s.id
                WHERE c.workspace_id = %s AND s.structural_kind = 'dialogue'
                  AND c.source_revision_id = (SELECT current_source_revision_id FROM omnix_audiobook_projects
                                               WHERE workspace_id = %s AND id = %s)
                ORDER BY c.ordinal, s.ordinal""",
            (account_a.workspace_id, account_a.workspace_id, project_id),
        ).fetchall()

    assert set(speakers) >= {"Mara", "Tomas"}
    assert ("the captain", "confirmed") in aliases
    assert lines == [("story-tide", "version-3", 4)]
    assert [(text.strip(), speaker, status, source) for text, speaker, status, source in spoken] == [
        ("“Hold fast.”", speakers["Mara"], "confident", "story"),
        ("“Aye, captain.”", speakers["Tomas"], "confident", "story"),
        # Not in the cast: with no model it falls back to the narrator, for review.
        ("“Who are you?”", narrator_id(project_id), "review_required", None),
        ("“Stay back.”", speakers["Mara"], "confident", "story"),
    ]

    # A rerun with no classifier decides only the story's own lines: one a classifier gave Tomas keeps him.
    with database.transaction() as connection:
        connection.execute("SELECT set_config('omnix.workspace_id', %s, true)", (account_a.workspace_id,))
        connection.execute(
            """INSERT INTO omnix_audiobook_annotations
                   (id, workspace_id, span_id, revision, role, speaker_id, speaker_candidate, delivery, evidence,
                    classifier, review_status)
               SELECT 'ab:an:classified-who', a.workspace_id, a.span_id, a.revision + 1, 'dialogue', %s::uuid,
                      NULL, a.delivery, '{}'::jsonb, '{}'::jsonb, 'confident'
                 FROM omnix_audiobook_spans s
                 JOIN LATERAL (SELECT * FROM omnix_audiobook_annotations
                                WHERE workspace_id = s.workspace_id AND span_id = s.id
                                ORDER BY revision DESC LIMIT 1) a ON TRUE
                WHERE s.workspace_id = %s AND btrim(s.source_text) = '“Who are you?”'""",
            (speakers["Tomas"], account_a.workspace_id),
        )
    service.reclassify_source(account_a, project_id=project_id)
    assert worker.run_analyze_once(database, account_a, worker_id="test")
    with database.transaction() as connection:
        connection.execute("SELECT set_config('omnix.workspace_id', %s, true)", (account_a.workspace_id,))
        latest = dict(connection.execute(
            """SELECT btrim(s.source_text), a.speaker_id::text
                 FROM omnix_audiobook_spans s
                 JOIN LATERAL (SELECT speaker_id FROM omnix_audiobook_annotations
                                WHERE workspace_id = s.workspace_id AND span_id = s.id
                                ORDER BY revision DESC LIMIT 1) a ON TRUE
                WHERE s.workspace_id = %s AND s.structural_kind = 'dialogue'""",
            (account_a.workspace_id,),
        ).fetchall())
    assert latest["“Who are you?”"] == speakers["Tomas"]
    assert latest["“Hold fast.”"] == speakers["Mara"]


def test_a_member_another_goes_by_keeps_their_own_voice(two_accounts, monkeypatch, tmp_path):
    """ST-4.4: an alias that is another member's name stays that member's, and the import says it was left out."""
    from app.apps.audiobook import routes
    from app.apps.audiobook.story_import import StoryImport
    from app.persistence.blob_store import LocalBlobStore
    from app.runtime.tenant_context import pop_tenant, push_tenant

    database, account_a, _ = two_accounts
    monkeypatch.setattr(routes, "default_database", lambda: database)
    monkeypatch.setattr(routes, "default_blob_store", lambda: LocalBlobStore(tmp_path))
    monkeypatch.setattr(routes, "_SERVICE", None)
    story = {**STORY, "cast": [{"name": "Mara", "aliases": ["the captain", "Tomas"]}, {"name": "Tomas"}]}
    token = push_tenant(account_a)
    try:
        created = routes.import_story(StoryImport.model_validate(story))
    finally:
        pop_tenant(token)
    with database.transaction() as connection:
        connection.execute("SELECT set_config('omnix.workspace_id', %s, true)", (account_a.workspace_id,))
        speakers = {row[0] for row in connection.execute(
            "SELECT canonical_name FROM omnix_audiobook_speakers WHERE project_id = %s AND status = 'active'",
            (str(created["id"]),),
        ).fetchall()}
        aliases = {row[0] for row in connection.execute(
            "SELECT alias FROM omnix_audiobook_speaker_aliases WHERE project_id = %s AND status = 'confirmed'",
            (str(created["id"]),),
        ).fetchall()}
    assert {"Mara", "Tomas"} <= speakers
    assert aliases == {"the captain"}
    assert created["skipped_aliases"] == ["Tomas"]

