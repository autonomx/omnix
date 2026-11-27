"""Story projects on PostgreSQL (ST-1.1 to ST-1.6): pages, versions, retries, trash, import and accounts."""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

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
    workspaces = [f"workspace:story-{name}-{uuid.uuid4().hex[:10]}" for name in ("a", "b")]
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
            connection.execute("DELETE FROM omnix_workspaces WHERE id = ANY(%s)", (workspaces,))
        database.close()


@contextmanager
def _as(context):
    from app.runtime.tenant_context import pop_tenant, push_tenant

    token = push_tenant(context)
    try:
        yield
    finally:
        pop_tenant(token)


def _texts(project):
    return [block.text for page in project.pages if not page.hidden for block in page.blocks]


def _pages(*texts, title=None):
    return [{"title": title, "blocks": [{"kind": "narration", "text": text}]} for text in texts]


def test_a_page_job_keeps_its_speakers_moves_and_proposed_cast(two_accounts):
    from app.apps.story import service
    from app.apps.story.contracts import StoryProjectCreate

    database, account, _ = two_accounts
    blocks = [{"kind": "narration", "text": "Dusk."},
              {"kind": "dialogue", "speaker_id": "mara", "text": "“Who?”"},
              {"kind": "dialogue", "speaker_id": "ghost", "text": "“Me.”", "attribution": "unverified"}]
    with _as(account):
        project = service.create_project(database, account, StoryProjectCreate(premise="p", mode="interactive"))
        service.replace_characters(database, account, project.id, [{"id": "mara", "name": "Mara"}])
        service.record_job_result(
            database, account, project_id=project.id, job_id="job-s", action="continue", interaction_mode="story",
            title=None, pages=[{"title": "", "blocks": blocks, "suggested_moves": ["Run", "Hide"]}],
            player_text="I listen.", new_characters=[{"id": "wren", "name": "Wren", "description": "A girl."},
                                                     {"id": "mara", "name": "Mara"}])
        # Two pages of a rewrite stay two pages in the version, each in its chapter.
        ref = service.record_job_result(
            database, account, project_id=project.id, job_id="job-v", action="rewrite", interaction_mode="writing",
            title=None, pages=[{"chapter": 1, "title": "One", "blocks": blocks[:1]},
                               {"chapter": 2, "title": "Two", "blocks": blocks[1:2]}], player_text=None)
        stored = service.get_project(database, account, project.id)
        version = service.get_version(database, account, project.id, ref["version_id"])
        with pytest.raises(ValueError):
            service.record_job_result(database, account, project_id=project.id, job_id="job-e", action="continue",
                                      interaction_mode="story", title=None, pages=[{"blocks": []}], player_text=None)

    page = stored.pages[0]
    assert [(block.kind, block.speaker_id, block.attribution) for block in page.blocks] == [
        ("narration", None, None), ("dialogue", "mara", None), ("dialogue", "ghost", "unverified")]
    assert page.suggested_moves == ["Run", "Hide"]
    assert [(character.id, character.suggested) for character in stored.characters] == [
        ("mara", False), ("wren", True)]
    assert [(page.chapter, page.title) for page in version.pages] == [(1, "One"), (2, "Two")]


def test_job_pages_and_versions_are_written_once(two_accounts):
    from app.apps.story import service
    from app.apps.story.contracts import StoryProjectCreate

    database, account, _ = two_accounts
    with _as(account):
        project = service.create_project(database, account, StoryProjectCreate(premise="A courier.", mode="interactive"))
        job = dict(database=database, context=account, project_id=project.id, interaction_mode="story", title=None)
        first = service.record_job_result(**job, job_id="job-1", action="draft",
                                          pages=_pages("The road ran on.", title="Lantern Road"), player_text=None)
        again = service.record_job_result(**job, job_id="job-1", action="draft",
                                          pages=_pages("A second take.", title="Other"), player_text=None)
        assert again == first and "page_id" in first
        move = service.record_job_result(**job, job_id="job-2", action="continue", pages=_pages("She follows it."),
                                         player_text="I follow the road.", chosen_suggestion="Follow")
        service.record_job_result(**job, job_id="job-3", action="continue", pages=_pages("Night falls."),
                                  player_text="I make camp.")
        version = service.record_job_result(**job, job_id="job-4", action="rewrite", pages=_pages("A cleaner road."),
                                            player_text=None)
        assert service.record_job_result(**job, job_id="job-4", action="rewrite", pages=_pages("x"),
                                         player_text=None) == version
        stored = service.get_project(database, account, project.id)

    assert stored.title == "Lantern Road"
    assert _texts(stored) == ["The road ran on.", "She follows it.", "Night falls."]
    assert [move.player_text for move in stored.moves] == ["I follow the road.", "I make camp."]
    assert stored.moves[0].page_id == move["page_id"] and stored.moves[0].chosen_suggestion == "Follow"
    assert stored.moves[1].parent_move_id == stored.moves[0].id
    # A rewrite is kept as a version; the manuscript stays as it was until the writer restores it.
    assert [(summary.kind, summary.version_number) for summary in stored.versions] == [("rewrite", 1)]
    with _as(account):
        written = service.written_by_job(database, account, project.id, "job-4")
    assert written["ref"] == version and "A cleaner road." in written["content"]


def test_restoring_a_version_keeps_the_manuscript_it_replaces(two_accounts):
    from app.apps.story import service
    from app.apps.story.contracts import StoryProjectCreate

    database, account, _ = two_accounts
    with _as(account):
        project = service.create_project(database, account, StoryProjectCreate(title="T"))
        service.append_page(database, account, project.id, blocks=[{"kind": "narration", "text": "Draft one."}])
        ref = service.record_job_result(database, account, project_id=project.id, job_id="job-r", action="rewrite",
                                        interaction_mode="writing", title=None, pages=_pages("Draft two."),
                                        player_text=None)
        restored = service.restore_version(database, account, project.id, ref["version_id"])
        assert _texts(restored) == ["Draft two."]
        before = next(summary for summary in restored.versions if summary.title.startswith("Before restoring"))
        back = service.restore_version(database, account, project.id, before.id)
    assert _texts(back) == ["Draft one."]
    assert len(back.versions) == 3


def test_a_job_without_a_project_gets_one_of_its_own_once(two_accounts):
    from app.apps.story import service

    database, account, _ = two_accounts
    with _as(account):
        first = service.job_project(database, account, project_id=None, job_id="job-old", premise="p",
                                    mode="writing", tone=None, writing_style=None)
        again = service.job_project(database, account, project_id=None, job_id="job-old", premise="p",
                                    mode="writing", tone=None, writing_style=None)
        listed = service.list_projects(database, account)
    assert first["project"]["id"] == again["project"]["id"]
    assert [summary.origin_kind for summary in listed] == ["job"]


def test_trash_restore_and_purge(two_accounts):
    from app.apps.story import service
    from app.apps.story.contracts import StoryProjectCreate

    database, account, _ = two_accounts
    with _as(account):
        project = service.create_project(database, account, StoryProjectCreate(title="Gone soon"))
        with pytest.raises(service.StoryConflict, match="not_in_trash"):
            service.purge_project(database, account, project.id)
        service.set_trashed(database, account, project.id, True)
        assert [summary.id for summary in service.list_projects(database, account, trashed=True)] == [project.id]
        assert service.list_projects(database, account) == []
        with pytest.raises(service.StoryConflict, match="in_trash"):
            service.append_page(database, account, project.id, blocks=[{"text": "x"}])
        service.set_trashed(database, account, project.id, False)
        assert [summary.id for summary in service.list_projects(database, account)] == [project.id]
        service.set_trashed(database, account, project.id, True)
        service.purge_project(database, account, project.id)
        with pytest.raises(service.StoryNotFound):
            service.get_project(database, account, project.id)


def test_importing_twice_makes_each_story_once(two_accounts):
    from app.apps.story import service
    from app.apps.story.contracts import StoryCharacter, StoryImportItem

    database, account, _ = two_accounts
    items = [
        StoryImportItem(origin_kind="local", origin_ref="draft-1", premise="p", text="# Old Road\n\nOne.\n\nTwo."),
        StoryImportItem(origin_kind="asset", origin_ref="asset-9", title="Saved", text="Three.",
                        characters=[StoryCharacter(id="mara", name="Mara")]),
        StoryImportItem(origin_kind="job", origin_ref="job-binned", title="Binned", text="Four.", trashed=True),
    ]
    with _as(account):
        first = service.import_items(database, account, items)
        second = service.import_items(database, account, items)
        imported = [service.get_project(database, account, project_id) for project_id in first.created[:2]]
        trashed = [summary.title for summary in service.list_projects(database, account, trashed=True)]
    assert len(first.created) == 3 and first.existing == []
    # A story the browser had binned lands in the server's trash.
    assert trashed == ["Binned"]
    assert second.created == [] and sorted(second.existing) == sorted(first.created)
    assert [(project.title, _texts(project)) for project in imported] == [("Old Road", ["One.", "Two."]),
                                                                         ("Saved", ["Three."])]
    assert [character.name for character in imported[1].characters] == ["Mara"]


def test_an_import_is_cleaned_and_a_long_one_split_into_pages(two_accounts):
    """An imported story's text holds no control characters, and no page more blocks than a page allows."""
    from app.apps.story import service
    from app.apps.story.contracts import BLOCKS_MAX, StoryImportItem

    database, account, _ = two_accounts
    paragraphs = ["Bell\x0b rang.\x07", *(f"Line {number}." for number in range(BLOCKS_MAX + 4))]
    with _as(account):
        result = service.import_items(database, account, [
            StoryImportItem(origin_kind="local", origin_ref="long-draft", title="Long", text="\n\n".join(paragraphs))])
        project = service.get_project(database, account, result.created[0])
    assert [len(page.blocks) for page in project.pages] == [BLOCKS_MAX, 5]
    assert _texts(project)[0] == "Bell rang." and _texts(project)[-1] == f"Line {BLOCKS_MAX + 3}."
    assert len(_texts(project)) == BLOCKS_MAX + 5


def test_cast_and_notes_are_replaced_whole(two_accounts):
    from app.apps.story import service
    from app.apps.story.contracts import StoryNoteInput, StoryProjectCreate

    database, account, _ = two_accounts
    with _as(account):
        project = service.create_project(database, account, StoryProjectCreate())
        with pytest.raises(service.StoryConflict, match="repeat"):
            service.replace_characters(database, account, project.id,
                                       [{"id": "a", "name": "A"}, {"id": "a", "name": "B"}])
        service.replace_characters(database, account, project.id, [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}])
        cast = service.replace_characters(database, account, project.id, [{"id": "b", "name": "Bea"}])
        noted = service.replace_notes(database, account, project.id, [StoryNoteInput(title="Map", body="North")])
        kept = service.replace_notes(database, account, project.id,
                                     [StoryNoteInput(id=noted.notes[0].id, title="Map", body="South"),
                                      StoryNoteInput(id="someone-elses", title="New")])
    assert [(character.id, character.name) for character in cast.characters] == [("b", "Bea")]
    assert noted.notes[0].id in {note.id for note in kept.notes}
    assert "someone-elses" not in {note.id for note in kept.notes}
    assert {note.body for note in kept.notes} == {"South", ""}


def test_one_account_cannot_read_or_change_anothers_story(two_accounts, monkeypatch):
    from fastapi import HTTPException

    from app.apps.story import routes
    from app.apps.story.contracts import StoryPageCreate, StoryProjectCreate

    database, account_a, account_b = two_accounts
    monkeypatch.setattr(routes, "default_database", lambda: database)
    with _as(account_a):
        project = routes.create_story_project(StoryProjectCreate(title="A's story"))
        routes.append_story_page(project.id, StoryPageCreate(blocks=[{"text": "Mine."}]))
    with _as(account_b):
        assert routes.list_story_projects(trashed=False).projects == []
        for call in (lambda: routes.get_story_project(project.id),
                     lambda: routes.append_story_page(project.id, StoryPageCreate(blocks=[{"text": "Yours."}])),
                     lambda: routes.trash_story_project(project.id),
                     lambda: routes.undo_story_move(project.id),
                     lambda: routes.open_story_page(project.id, project.pages[0].id if project.pages else "x")):
            with pytest.raises(HTTPException) as refused:
                call()
            assert refused.value.status_code == 404
    with _as(account_a):
        assert _texts(routes.get_story_project(project.id)) == ["Mine."]


def test_undo_and_branches_keep_every_page_and_each_run_its_own_summary(two_accounts, monkeypatch):
    """ST-3.3, ST-3.4, ST-3.6: undo hides the last move's page, an earlier page opens its run, a run is kept."""
    from fastapi import HTTPException

    from app.apps.story import routes, service
    from app.apps.story.contracts import StoryProjectCreate, StoryVersionCreate

    database, account, _ = two_accounts
    monkeypatch.setattr(routes, "default_database", lambda: database)

    def write(job_id, text, move=None):
        service.record_job_result(
            database, account, project_id=project.id, job_id=job_id, action="continue" if move else "draft",
            interaction_mode="story", title=None, player_text=move,
            pages=[{"blocks": [{"kind": "narration", "text": text}], "summary": f"So far: {text}"}])

    with _as(account):
        project = routes.create_story_project(StoryProjectCreate(premise="A courier.", mode="interactive"))
        with pytest.raises(HTTPException) as nothing:
            routes.undo_story_move(project.id)
        assert nothing.value.status_code == 409
        write("job-0", "The road.")
        with pytest.raises(HTTPException) as opening:
            routes.undo_story_move(project.id)  # the opening page is no one's move
        assert opening.value.status_code == 409
        write("job-1", "The left fork.", "I go left.")
        write("job-2", "A bridge.", "I cross.")
        undone = routes.undo_story_move(project.id)
        assert _texts(undone) == ["The road.", "The left fork."]
        write("job-3", "A ford.", "I wade.")
        branched = routes.get_story_project(project.id)
        opening_page = branched.pages[0]
        # Back to before the first move, and a different one from there.
        assert _texts(routes.open_story_page(project.id, opening_page.id)) == ["The road."]
        write("job-4", "The right fork.", "I go right.")
        right = routes.get_story_project(project.id)
        context = service.job_project(database, account, project_id=project.id, job_id="job-5", premise="p",
                                      mode="interactive", tone=None, writing_style=None)
        # Back to the bridge: the run that ends there, and its own summary.
        bridge = next(page for page in right.pages if page.blocks[0].text == "A bridge.")
        bridge_run = routes.open_story_page(project.id, bridge.id)
        bridge_context = service.job_project(database, account, project_id=project.id, job_id="job-6", premise="p",
                                             mode="interactive", tone=None, writing_style=None)
        kept = routes.save_story_version(project.id, StoryVersionCreate(title="The bridge run", kind="kept_run"))
        kept_version = routes.get_story_version(project.id, kept.versions[-1].id)
        with pytest.raises(HTTPException) as missing:
            routes.open_story_page(project.id, "page-missing")
        assert missing.value.status_code == 404

    assert _texts(right) == ["The road.", "The right fork."]
    assert [page["summary"] for page in context["pages"]][-1] == "So far: The right fork."
    assert _texts(bridge_run) == ["The road.", "The left fork.", "A bridge."]
    assert bridge_context["pages"][-1]["summary"] == "So far: A bridge."
    # Nothing was deleted: five pages, each continuing from the one before it in its run.
    assert len(bridge_run.pages) == 5
    parents = {page.blocks[0].text: page.parent_page_id for page in bridge_run.pages}
    ids = {page.blocks[0].text: page.id for page in bridge_run.pages}
    assert parents == {"The road.": None, "The left fork.": ids["The road."], "A bridge.": ids["The left fork."],
                       "A ford.": ids["The left fork."], "The right fork.": ids["The road."]}
    # The move that opened the right fork follows no move: it was made from the opening page.
    right_move = next(move for move in bridge_run.moves if move.player_text == "I go right.")
    assert right_move.parent_move_id is None
    assert kept.versions[-1].kind == "kept_run" and kept.versions[-1].title == "The bridge run"
    assert [page.blocks[0].text for page in kept_version.pages] == ["The road.", "The left fork.", "A bridge."]


def test_retention_deletes_only_long_trashed_projects(two_accounts):
    from app.apps.story import repository, service
    from app.apps.story.contracts import StoryProjectCreate
    from app.persistence.tenant_scope import system_scope

    database, account, _ = two_accounts
    with _as(account):
        old = service.create_project(database, account, StoryProjectCreate(title="Old"))
        recent = service.create_project(database, account, StoryProjectCreate(title="Recent"))
        live = service.create_project(database, account, StoryProjectCreate(title="Live"))
        service.append_page(database, account, old.id, blocks=[{"text": "x"}])
        for project in (old, recent):
            service.set_trashed(database, account, project.id, True)
    with system_scope("retention"), database.transaction() as connection:
        connection.execute("UPDATE omnix_story_projects SET deleted_at = CURRENT_TIMESTAMP - INTERVAL '31 days' "
                           "WHERE id = %s", (old.id,))
        assert repository.delete_trashed_projects(connection, 30, 100) >= 1
        remaining = {row[0] for row in connection.execute(
            "SELECT id FROM omnix_story_projects WHERE workspace_id = %s", (account.workspace_id,)).fetchall()}
        pages = connection.execute("SELECT count(*) FROM omnix_story_pages WHERE project_id = %s",
                                   (old.id,)).fetchone()[0]
    assert remaining == {recent.id, live.id} and pages == 0


class _FakeModel:
    """The story job's model: a plan for the planning job, a page with a summary for a page."""

    def __init__(self):
        self.prompts = []

    def __call__(self, prompt, contract, budget, *, what, provider_id, model_id):
        from app.apps.story.outline import StoryOutlineReply
        from app.apps.story.page_contract import StoryPageReply

        self.prompts.append((what, prompt.user))
        if what == "outline":
            return StoryOutlineReply.model_validate({"chapters": [
                {"title": "The Ford", "beats": ["Mara reaches the river.", "  ", "She crosses at dusk."]},
                {"title": "", "beats": []},
                {"title": "The Far Bank", "beats": ["A stranger waits."]},
            ]}), "fake"
        number = len([entry for entry in self.prompts if entry[0] == "page"]) - 1
        return StoryPageReply.model_validate({
            "blocks": [{"kind": "narration", "text": f"Page {number}."}], "summary": f"Through page {number}.",
        }), "fake"


def _run_job(job_id, **payload):
    from types import SimpleNamespace

    from app.apps.story import jobs

    return jobs._render_story(SimpleNamespace(id=job_id), {"premise": "A river crossing.", **payload},
                              provider_id=None, model_id=None)


def test_a_plan_is_made_edited_and_drafted_beat_by_beat(two_accounts, monkeypatch):
    """ST-5.1: a planning job stores the outline once, the writer edits it, and each beat drafts its page."""
    from fastapi import HTTPException

    import app.persistence.database as persistence_database
    from app.apps.story import jobs, routes
    from app.apps.story.contracts import StoryOutlineReplace, StoryProjectCreate

    database, account, other = two_accounts
    model = _FakeModel()
    monkeypatch.setattr(routes, "default_database", lambda: database)
    monkeypatch.setattr(persistence_database, "default_database", lambda: database)
    monkeypatch.setattr(jobs, "_generate", model)
    with _as(account):
        project = routes.create_story_project(StoryProjectCreate(title="The Ford", premise="A river crossing."))
        planned = _run_job("job-plan", project_id=project.id, action="outline", outline_chapters=3)
        again = _run_job("job-plan", project_id=project.id, action="outline", outline_chapters=3)
        outline = routes.get_story_project(project.id).outline
        first, second = outline[0].beats[0], outline[0].beats[1]
        edited = routes.replace_story_outline(project.id, StoryOutlineReplace.model_validate({"chapters": [
            {"title": "The Ford", "beats": [{"id": first.id, "text": "Mara reaches the flooded river."},
                                            {"id": second.id, "text": second.text}]},
            {"title": "The Crossing", "beats": [{"id": "made-up", "text": "The rope snaps."}]},
            {"title": "The Far Bank", "beats": [{"id": outline[1].beats[0].id, "text": "A stranger waits."}]},
        ]}))
        _run_job("job-beat-1", project_id=project.id, action="continue", beat_id=first.id)
        crossing = edited.outline[1].beats[0]
        _run_job("job-beat-2", project_id=project.id, action="continue", beat_id=crossing.id)
        drafted = routes.get_story_project(project.id)
        with pytest.raises(ValueError, match="story_beat_not_found"):
            _run_job("job-beat-x", project_id=project.id, beat_id="beat_missing")
        # Saving the plan again keeps the page a beat was drafted into.
        resaved = routes.replace_story_outline(project.id, StoryOutlineReplace.model_validate(
            {"chapters": [chapter.model_dump() for chapter in drafted.outline]}))
    with _as(other):
        with pytest.raises(HTTPException) as refused:
            routes.replace_story_outline(project.id, StoryOutlineReplace())
        assert refused.value.status_code == 404

    # The plan: empty beats and a chapter with none are dropped; a retried job doesn't plan again.
    assert planned["artifact_type"] == "story_outline" and again["story_ref"] == planned["story_ref"]
    assert [entry[0] for entry in model.prompts].count("outline") == 1
    assert "as 3 chapters" in model.prompts[0][1] and "<premise>\nA river crossing.\n</premise>" in model.prompts[0][1]
    assert [(chapter.chapter, chapter.title, [beat.text for beat in chapter.beats]) for chapter in outline] == [
        (1, "The Ford", ["Mara reaches the river.", "She crosses at dusk."]), (2, "The Far Bank", ["A stranger waits."])]
    # The edit: known beats keep their ids, an unknown id is a new beat, chapters are numbered by place.
    assert [chapter.chapter for chapter in edited.outline] == [1, 2, 3]
    assert edited.outline[0].beats[0].id == first.id and edited.outline[0].beats[0].text.endswith("flooded river.")
    assert crossing.id not in {"made-up", first.id, second.id}
    assert edited.outline[2].beats[0].id == outline[1].beats[0].id
    # Each beat drafted its page in its own chapter; the second opened chapter 2 from the summary.
    pages = [page for page in drafted.pages if not page.hidden]
    assert [(page.chapter, page.blocks[0].text) for page in pages] == [(1, "Page 0."), (2, "Page 1.")]
    beat_prompts = [text for what, text in model.prompts if what == "page"]
    assert "Write the opening page" in beat_prompts[0]
    assert "<beat>\nChapter 1: The Ford\nMara reaches the flooded river.\n</beat>" in beat_prompts[0]
    assert "Begin chapter 2 here" in beat_prompts[1] and "<summary>\nThrough page 0.\n</summary>" in beat_prompts[1]
    assert "<beat>\nChapter 2: The Crossing\nThe rope snaps.\n</beat>" in beat_prompts[1]
    linked = {beat.id: beat.page_id for chapter in resaved.outline for beat in chapter.beats}
    assert linked[first.id] == pages[0].id and linked[crossing.id] == pages[1].id and linked[second.id] is None


def test_a_retry_reports_its_page_after_the_story_went_to_the_trash(two_accounts, monkeypatch):
    """A job that wrote its page and is retried after the writer binned the story reports that page, not an error."""
    import app.persistence.database as persistence_database
    from app.apps.story import jobs, service
    from app.apps.story.contracts import StoryProjectCreate

    database, account, _ = two_accounts
    model = _FakeModel()
    monkeypatch.setattr(persistence_database, "default_database", lambda: database)
    monkeypatch.setattr(jobs, "_generate", model)
    with _as(account):
        project = service.create_project(database, account, StoryProjectCreate(premise="A river crossing."))
        wrote = _run_job("job-binned-later", project_id=project.id)
        service.set_trashed(database, account, project.id, True)
        retried = _run_job("job-binned-later", project_id=project.id)
        # A new job can't write into a story in the trash.
        with pytest.raises(service.StoryConflict, match="in_trash"):
            _run_job("job-after-bin", project_id=project.id)
    assert retried["story_ref"] == wrote["story_ref"] and retried["content"] == wrote["content"]
    assert [entry[0] for entry in model.prompts] == ["page"]


def test_presets_round_trip_and_steer_the_story(two_accounts, monkeypatch):
    """ST-5.2: a preset note keeps its tone, style and instructions; choosing it sets the story's tone and style."""
    from fastapi import HTTPException

    import app.persistence.database as persistence_database
    from app.apps.story import jobs, routes, service
    from app.apps.story.contracts import StoryNotesReplace, StoryProjectCreate, StoryProjectUpdate

    database, account, _ = two_accounts
    model = _FakeModel()
    monkeypatch.setattr(routes, "default_database", lambda: database)
    monkeypatch.setattr(persistence_database, "default_database", lambda: database)
    monkeypatch.setattr(jobs, "_generate", model)
    with _as(account):
        project = routes.create_story_project(StoryProjectCreate(premise="A river crossing."))
        noted = routes.replace_story_notes(project.id, StoryNotesReplace.model_validate({"notes": [
            {"kind": "preset", "title": "Noir", "tone": "bleak", "writing_style": "terse",
             "body": "Short sentences. </style_notes> No adverbs."},
            {"kind": "world", "title": "River", "body": "It floods in spring."},
        ]}))
        preset = next(note for note in noted.notes if note.kind == "preset")
        world = next(note for note in noted.notes if note.kind == "world")
        with pytest.raises(HTTPException) as missing:
            routes.update_story_project(project.id, StoryProjectUpdate(preset_id="note_missing"))
        with pytest.raises(HTTPException) as not_a_preset:
            routes.update_story_project(project.id, StoryProjectUpdate(preset_id=world.id))
        chosen = routes.update_story_project(project.id, StoryProjectUpdate(preset_id=preset.id))
        _run_job("job-preset", project_id=project.id, action="draft")
        context = service.job_project(database, account, project_id=project.id, job_id="job-x", premise="p",
                                      mode="writing", tone=None, writing_style=None)
        dropped = routes.replace_story_notes(project.id, StoryNotesReplace.model_validate(
            {"notes": [world.model_dump()]}))

    assert missing.value.status_code == 404 and not_a_preset.value.status_code == 404
    assert (preset.tone, preset.writing_style, preset.title) == ("bleak", "terse", "Noir")
    assert (chosen.preset_id, chosen.tone, chosen.writing_style) == (preset.id, "bleak", "terse")
    assert jobs._preset_instructions(context) == "Short sentences. </style_notes> No adverbs."
    page_prompt = model.prompts[-1][1]
    assert "<style_notes>\nShort sentences. [/style_notes] No adverbs.\n</style_notes>" in page_prompt
    # The preset's instructions steer style only: they are not world notes.
    assert "Short sentences" not in page_prompt.split("<world>")[1].split("</world>")[0]
    assert dropped.preset_id == "" and [note.kind for note in dropped.notes] == ["world"]


def test_a_story_exports_as_a_book_file_to_its_own_account_only(two_accounts, monkeypatch):
    """ST-6.5: each format is an attachment with its media type; another account gets 404."""
    from fastapi import HTTPException

    from app.apps.story import routes
    from app.apps.story.contracts import StoryPageCreate, StoryProjectCreate

    database, account_a, account_b = two_accounts
    monkeypatch.setattr(routes, "default_database", lambda: database)
    with _as(account_a):
        project = routes.create_story_project(StoryProjectCreate(title="Low Tide"))
        routes.append_story_page(project.id, StoryPageCreate(blocks=[{"text": "The boat drifts."}]))
        files = {fmt: routes.export_story(project.id, fmt) for fmt in ("epub", "docx", "pdf")}
    with _as(account_b):
        with pytest.raises(HTTPException) as refused:
            routes.export_story(project.id, "pdf")

    assert refused.value.status_code == 404
    assert {fmt: response.media_type for fmt, response in files.items()} == {
        "epub": "application/epub+zip",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
    }
    assert files["pdf"].headers["content-disposition"] == 'attachment; filename="low-tide.pdf"'
    assert files["pdf"].body.startswith(b"%PDF-") and files["epub"].body[30:50].startswith(b"mimetype")


def test_an_edit_keeps_its_tags_and_a_selection_is_proposed_then_answered(two_accounts, monkeypatch):
    """ST-6.1, ST-6.2: a page edit keeps each speaker tag; a selection job proposes blocks for its range alone,
    which the writer accepts into that range or rejects, and a page changed since cannot be accepted."""
    from fastapi import HTTPException
    from pydantic import ValidationError

    import app.persistence.database as persistence_database
    from app.apps.story import jobs, routes
    from app.apps.story.contracts import StoryPageCreate, StoryPageUpdate, StoryProjectCreate

    database, account, other = two_accounts
    model = _FakeModel()
    monkeypatch.setattr(routes, "default_database", lambda: database)
    monkeypatch.setattr(persistence_database, "default_database", lambda: database)
    monkeypatch.setattr(jobs, "_generate", model)
    blocks = [{"kind": "narration", "text": "Dusk."},
              {"kind": "dialogue", "speaker_id": "mara", "text": "“Who?”", "attribution": "tagged"},
              {"kind": "narration", "text": "Wind."}]
    with _as(account):
        project = routes.create_story_project(StoryProjectCreate(title="The Gate", premise="A river crossing."))
        page_id = routes.append_story_page(project.id, StoryPageCreate(blocks=blocks)).pages[0].id
        edited = routes.update_story_page(project.id, page_id, StoryPageUpdate.model_validate(
            {"blocks": [blocks[0], {**blocks[1], "text": "“Who\x0b goes?”"}, blocks[2]], "base_blocks": blocks}))
        # An edit opened before that one names the old blocks as its base, so it is refused; so is an edit
        # that names no base, and `hidden` is not something an edit sets.
        with pytest.raises(HTTPException) as overwritten:
            routes.update_story_page(project.id, page_id, StoryPageUpdate.model_validate(
                {"blocks": [{"kind": "narration", "text": "Gone."}], "base_blocks": blocks}))
        with pytest.raises(ValidationError):
            StoryPageUpdate.model_validate({"blocks": [{"kind": "narration", "text": "Gone."}]})
        with pytest.raises(ValidationError):
            StoryPageUpdate.model_validate({"blocks": [{"kind": "narration", "text": "  "}], "base_blocks": blocks})
        still_shown = routes.update_story_page(project.id, page_id, StoryPageUpdate.model_validate({"hidden": True}))
        selection = {"page_id": page_id, "start": 1, "end": 2, "texts": ["“Who goes?”"]}
        # A selection whose text the page no longer holds at those indices is not reworked.
        with pytest.raises(ValueError, match="story_selection_page_changed"):
            _run_job("job-sel-old", project_id=project.id, action="rewrite", selection={**selection, "texts": ["“Who?”"]})
        first = _run_job("job-sel-1", project_id=project.id, action="rewrite", selection=selection)
        proposed = routes.get_story_project(project.id)
        rejected = routes.reject_story_selection(project.id, first["story_ref"]["version_id"])
        with pytest.raises(HTTPException) as answered:
            routes.accept_story_selection(project.id, first["story_ref"]["version_id"])
        second = _run_job("job-sel-2", project_id=project.id, action="dialogue", selection=selection)
        accepted = routes.accept_story_selection(project.id, second["story_ref"]["version_id"])
        third = _run_job("job-sel-3", project_id=project.id, action="expand",
                         selection={"page_id": page_id, "start": 0, "end": 1, "texts": ["Dusk."]})
        accepted_blocks = accepted.pages[0].model_dump()["blocks"]
        routes.update_story_page(project.id, page_id, StoryPageUpdate.model_validate(
            {"blocks": [{"kind": "narration", "text": "Night."}, *accepted_blocks[1:]], "base_blocks": accepted_blocks}))
        with pytest.raises(HTTPException) as changed:
            routes.accept_story_selection(project.id, third["story_ref"]["version_id"])
        for bad in ({"page_id": page_id, "start": 2, "end": 9}, {"page_id": page_id, "start": 1, "end": 1},
                    {"page_id": page_id, "start": True, "end": 2}, "all", {"page_id": page_id, "start": 0, "end": 1},
                    {"page_id": page_id, "start": 0, "end": 1, "texts": "Night."}):
            with pytest.raises(ValueError, match="story_selection_invalid"):
                _run_job("job-sel-bad", project_id=project.id, action="rewrite", selection=bad)
        with pytest.raises(ValueError, match="story_selection_page_not_found"):
            _run_job("job-sel-gone", project_id=project.id, action="rewrite",
                     selection={"page_id": "page_missing", "start": 0, "end": 1})
    with _as(other):
        with pytest.raises(HTTPException) as refused:
            routes.reject_story_selection(project.id, third["story_ref"]["version_id"])

    # The edit kept the spoken line's speaker and how it was tagged, and dropped the control character.
    assert [(block.kind, block.speaker_id, block.attribution, block.text) for block in edited.pages[0].blocks] == [
        ("narration", None, None, "Dusk."), ("dialogue", "mara", "tagged", "“Who goes?”"),
        ("narration", None, None, "Wind.")]
    # The stale edit was refused, and the page was not hidden.
    assert overwritten.value.status_code == 409 and "story_page_changed" in str(overwritten.value.detail)
    assert [page.hidden for page in still_shown.pages] == [False]
    # The job read only the selected line, with the text around it quoted, and proposed it as a version.
    prompt = [text for what, text in model.prompts if what == "page"][0]
    assert "<page>\n[mara] “Who goes?”\n</page>" in prompt and "a passage the writer selected" in prompt
    assert "<story>\nDusk.\n</story>" in prompt and "<after>\nWind.\n</after>" in prompt
    assert first["content"] == "Page 0."
    assert _texts(proposed) == ["Dusk.", "“Who goes?”", "Wind."]
    pending = next(version for version in proposed.versions if version.selection)
    assert (pending.kind, pending.selection.status, pending.selection.start, pending.selection.end) == (
        "rewrite", "pending", 1, 2)
    assert [block.text for block in pending.selection.original] == ["“Who goes?”"]
    assert [block.text for block in pending.selection.proposed] == ["Page 0."]
    # Rejecting left the page alone; an answered proposal cannot be answered again.
    assert _texts(rejected) == _texts(proposed)
    assert next(v for v in rejected.versions if v.id == pending.id).selection.status == "rejected"
    assert answered.value.status_code == 409 and "story_selection_not_pending" in str(answered.value.detail)
    # Accepting changed only the selected line and kept the story before it as a version.
    assert _texts(accepted) == ["Dusk.", "Page 1.", "Wind."]
    assert any(version.title == "Before accepting version 2" for version in accepted.versions)
    # A page changed since the job read it is a conflict, and another account cannot see the proposal.
    assert changed.value.status_code == 409 and "story_selection_page_changed" in str(changed.value.detail)
    assert refused.value.status_code == 404
