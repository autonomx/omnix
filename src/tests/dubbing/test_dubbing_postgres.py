"""Dubbing's projects and lines in PostgreSQL: revisions, approvals, re-runs and isolation (Phase 6)."""
from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="PostgreSQL integration tests need OMNIX_TEST_DATABASE_URL",
)


@pytest.fixture
def workspace():
    """An isolated workspace, installed as the tenant, with its database as the default."""
    from app.persistence import database as database_module
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.identity_service import PostgresIdentityRepository, ensure_local_identity
    from app.persistence.job_store import PostgresJobStoreAdapter
    from app.persistence.tenant_scope import system_scope
    from app.runtime.tenant_context import pop_tenant, push_tenant

    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_max=4))
    ensure_local_identity(database)
    seed = PostgresJobStoreAdapter(database)
    workspace_id = f"workspace:dubbing:{uuid.uuid4().hex}"
    with system_scope("identity.provision"), database.transaction() as connection:
        connection.execute("INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, 'Dubbing test', %s)",
                           (workspace_id, seed.context.user_id))
        connection.execute(
            "INSERT INTO omnix_workspace_memberships (id, workspace_id, user_id, roles) VALUES (%s, %s, %s, %s)",
            (f"membership:{uuid.uuid4().hex}", workspace_id, seed.context.user_id, ["owner", "admin", "member"]),
        )
        context = PostgresIdentityRepository(connection).load_context(user_id=seed.context.user_id,
                                                                      workspace_id=workspace_id)
    original = database_module.default_database
    database_module.default_database = lambda: database  # type: ignore[assignment]
    token = push_tenant(context)
    try:
        yield database, context
    finally:
        pop_tenant(token)
        database_module.default_database = original  # type: ignore[assignment]
        with system_scope("identity.provision"), database.transaction() as connection:
            connection.execute("DELETE FROM omnix_workspaces WHERE id = %s", (workspace_id,))
        database.close()


def _lines(*texts: tuple[str, float, float, str]) -> list[dict[str, Any]]:
    from app.apps.dubbing.steps import source_key

    return [{"source_key": source_key(speaker, start, text), "speaker": speaker, "start_seconds": start,
             "end_seconds": end, "source_text": text} for speaker, start, end, text in texts]


def _project(database: Any, context: Any) -> Any:
    from app.apps.dubbing import service

    project = service.create_project(database, context, title="Planning call", source_asset_id="dubbing-source:x",
                                     source_language="en", target_language="es")
    service.apply_step_result(database, context, project.id, {"lines": _lines(
        ("Speaker 1", 0.0, 3.0, "Good morning."), ("Speaker 2", 3.5, 6.0, "Thanks for having me."))})
    return project


def test_a_line_is_approved_only_with_a_take_of_its_current_words(workspace) -> None:
    from app.apps.dubbing import service

    database, context = workspace
    project = _project(database, context)
    first, second = service.get_project(database, context, project.id).segments
    service.apply_step_result(database, context, project.id, {"translations": {first.id: "Buenos días.",
                                                                               second.id: "Gracias por invitarme."}})
    with pytest.raises(service.DubbingConflict):
        service.set_approval(database, context, project.id, [first.id], True)  # no take yet
    line = service.get_project(database, context, project.id).segments[0]
    assert line.translation_revision == 1 and line.translation_origin == "llm"
    service.save_take(database, context, project.id, first.id, asset_id="take:1", revision=1, seconds=2.9,
                      fit_status="fits", fit_ratio=0.97, shortenings=0)
    approved = service.set_approval(database, context, project.id, [first.id], True)
    assert approved.segments[0].approved and approved.approved_count == 1

    # A person changes the words: the approval no longer counts, and the take is stale.
    edited = service.edit_line(database, context, project.id, first.id, translation="Muy buenos días.")
    line = edited.segments[0]
    assert line.translation_revision == 2 and line.translation_origin == "person"
    assert not line.approved and not line.take_current
    # The same words again do not bump the revision.
    again = service.edit_line(database, context, project.id, first.id, translation="Muy  buenos días.")
    assert again.segments[0].translation_revision == 2


def test_re_running_translation_leaves_approved_and_hand_edited_lines_alone(workspace) -> None:
    from types import SimpleNamespace

    from app.apps.dubbing import service, steps

    database, context = workspace
    project = _project(database, context)
    first, second = service.get_project(database, context, project.id).segments
    service.apply_step_result(database, context, project.id, {"translations": {first.id: "Buenos días.",
                                                                               second.id: "Gracias."}})
    service.save_take(database, context, project.id, first.id, asset_id="take:1", revision=1, seconds=3.0,
                      fit_status="fits", fit_ratio=1.0, shortenings=0)
    service.set_approval(database, context, project.id, [first.id], True)
    service.edit_line(database, context, project.id, second.id, translation="Gracias por invitarme.")

    class _Translator:
        def __init__(self) -> None:
            self.asked: list[str] = []

        def translate(self, lines: list[Any], **kwargs: Any) -> dict[str, str]:
            self.asked += [line.id for line in lines]
            return {line.id: f"NEW {line.text}" for line in lines}

    translator = _Translator()
    row, segments = service.load_for_step(database, context, project.id)
    run = steps.StepRun(SimpleNamespace(id="job", input_payload={"project_id": project.id}), None, row, segments)
    service.apply_step_result(database, context, project.id, steps.translate(run, translator))
    assert translator.asked == []  # nothing needed translating: one line approved, one a person's
    after = service.get_project(database, context, project.id).segments
    assert after[0].translation == "Buenos días." and after[0].approved
    assert after[1].translation == "Gracias por invitarme."

    # Asking for a line by id translates it again, even a person's.
    run = steps.StepRun(SimpleNamespace(id="job", input_payload={"project_id": project.id, "line_ids": [second.id]}),
                        None, *service.load_for_step(database, context, project.id))
    service.apply_step_result(database, context, project.id, steps.translate(run, translator))
    assert translator.asked == [second.id]
    assert service.get_project(database, context, project.id).segments[0].approved


def test_a_person_edit_made_while_translation_runs_is_kept(workspace) -> None:
    from types import SimpleNamespace

    from app.apps.dubbing import service, steps

    database, context = workspace
    project = _project(database, context)
    first, second = service.get_project(database, context, project.id).segments

    class _Translator:
        def translate(self, lines: list[Any], **kwargs: Any) -> dict[str, str]:
            # The person types the second line while the LLM is still working.
            service.edit_line(database, context, project.id, second.id, translation="Gracias, de verdad.")
            return {line.id: f"LLM {line.text}" for line in lines}

    run = steps.StepRun(SimpleNamespace(id="job", input_payload={"project_id": project.id}), None,
                        *service.load_for_step(database, context, project.id))
    service.apply_step_result(database, context, project.id, steps.translate(run, _Translator()))
    after = {line.id: line for line in service.get_project(database, context, project.id).segments}
    assert after[first.id].translation.startswith("LLM ") and after[first.id].translation_origin == "llm"
    assert after[second.id].translation == "Gracias, de verdad." and after[second.id].translation_origin == "person"


def test_re_transcription_keeps_lines_whose_words_did_not_change(workspace) -> None:
    from app.apps.dubbing import service

    database, context = workspace
    project = _project(database, context)
    first, _second = service.get_project(database, context, project.id).segments
    service.apply_step_result(database, context, project.id, {"translations": {first.id: "Buenos días."}})
    summary = service.apply_step_result(database, context, project.id, {"lines": _lines(
        ("Speaker 1", 0.0, 3.0, "Good morning."), ("Speaker 2", 3.5, 6.2, "Thanks for having me today."),
        ("Speaker 1", 6.5, 8.0, "Let's start."))})
    assert summary["lines"] == {"kept": 1, "added": 2, "removed": 1}
    lines = service.get_project(database, context, project.id).segments
    assert [line.position for line in lines] == [0, 1, 2]
    assert lines[0].id == first.id and lines[0].translation == "Buenos días."


def test_steps_and_assets_are_recorded_on_the_project(workspace) -> None:
    from app.apps.dubbing import service

    database, context = workspace
    project = _project(database, context)
    service.mark_step(database, context, project.id, "separate", "running", job_id="job:1")
    service.apply_step_result(database, context, project.id, {"assets": {"vocals": "a:v"}, "duration_seconds": 61.5})
    service.mark_step(database, context, project.id, "separate", "done", detail={"model": "roformer"})
    loaded = service.get_project(database, context, project.id)
    assert loaded.steps["separate"]["status"] == "done" and loaded.steps["separate"]["job_id"] == "job:1"
    assert loaded.assets == {"vocals": "a:v"} and loaded.duration_seconds == 61.5
    service.delete_project(database, context, project.id)
    with pytest.raises(service.DubbingNotFound):
        service.get_project(database, context, project.id)


def test_another_workspace_sees_no_dubbing_rows(workspace) -> None:
    """As a runtime-like role (no superuser, no BYPASSRLS), another workspace sees none of the project."""
    import psycopg

    from tests.support.database import admin_database_url

    database, context = workspace
    project = _project(database, context)
    role = "omnix_rls_probe"
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        if not admin.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
            pytest.skip("creating the probe role needs a superuser test database")
        admin.execute(f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS;
            END IF; END $$""")
        admin.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        admin.execute(f"GRANT SELECT ON omnix_dubbing_projects, omnix_dubbing_segments TO {role}")
    with psycopg.connect(admin_database_url(), autocommit=True) as probe:
        probe.execute(f"SET ROLE {role}")
        probe.execute("SELECT set_config('omnix.workspace_id', %s, false), set_config('omnix.system', '', false)",
                      (f"workspace:other:{uuid.uuid4().hex}",))
        assert probe.execute("SELECT 1 FROM omnix_dubbing_projects WHERE id = %s", (project.id,)).fetchall() == []
        assert probe.execute("SELECT 1 FROM omnix_dubbing_segments WHERE project_id = %s", (project.id,)).fetchall() == []
        probe.execute("SELECT set_config('omnix.workspace_id', %s, false)", (context.workspace_id,))
        assert len(probe.execute("SELECT 1 FROM omnix_dubbing_segments WHERE project_id = %s",
                                 (project.id,)).fetchall()) == 2


def test_shortening_never_replaces_words_a_person_wrote(workspace) -> None:
    """A machine rewrite applies only to the revision it read, and never to a person's words."""
    from app.apps.dubbing import service

    database, context = workspace
    project = _project(database, context)
    line = service.get_project(database, context, project.id).segments[0]
    revision = service.save_translation(database, context, project.id, line.id, "Buenos días a todos.", "llm")
    assert service.save_translation(database, context, project.id, line.id, "Buenos días.", "shortened",
                                    expected_revision=revision) == revision + 1
    # The same words again are "no shorter wording": the revision stands.
    assert service.save_translation(database, context, project.id, line.id, "Buenos días.", "shortened",
                                    expected_revision=revision + 1) == revision + 1
    # A stale revision (the line moved on) changes nothing.
    assert service.save_translation(database, context, project.id, line.id, "Hola.", "shortened",
                                    expected_revision=revision) is None
    service.edit_line(database, context, project.id, line.id, translation="Muy buenos días a todos ustedes.")
    current = service.get_project(database, context, project.id).segments[0]
    assert service.save_translation(database, context, project.id, line.id, "Días.", "shortened",
                                    expected_revision=current.translation_revision) is None
    kept = service.get_project(database, context, project.id).segments[0]
    assert kept.translation == "Muy buenos días a todos ustedes." and kept.translation_origin == "person"
