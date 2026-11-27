"""The storyteller's projects: what the routes and the story job do with them (ST-1.2 to ST-1.6)."""
from __future__ import annotations

import re
import uuid
from typing import Any

from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work

from .contracts import (
    BLOCKS_MAX,
    CHARACTERS_MAX,
    CONTROL_CHARS,
    StoryImportItem,
    StoryImportResult,
    StoryNoteInput,
    StoryOutlineChapterInput,
    StoryProject,
    StoryProjectCreate,
    StoryProjectSummary,
    StoryVersion,
)
from .repository import PostgresStoryRepository

#: Job actions whose result is a new version of the story rather than a new page (ST-1.6).
VERSION_ACTIONS = frozenset({"rewrite", "expand", "dialogue", "summarize"})


class StoryNotFound(LookupError):
    pass


class StoryConflict(RuntimeError):
    pass


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


# -- text and blocks ----------------------------------------------------------------------------


def text_to_blocks(text: str) -> list[dict[str, Any]]:
    """An imported Markdown manuscript as narration blocks, one per paragraph (its speakers are unknown).

    Control characters are dropped, as the API drops them when a page is read, so the stored text is the
    text a writer selects and edits.
    """
    paragraphs = (CONTROL_CHARS.sub("", part).strip() for part in re.split(r"\n\s*\n", text.replace("\r\n", "\n")))
    return [{"kind": "narration", "text": paragraph} for paragraph in paragraphs if paragraph]


def blocks_text(blocks: list[dict[str, Any]]) -> str:
    return "\n\n".join(str(block.get("text") or "").strip() for block in blocks if str(block.get("text") or "").strip())


def split_title(text: str) -> tuple[str | None, str]:
    """A leading level-1 heading is the title; the rest is the text."""
    lines = text.strip().splitlines()
    if lines and lines[0].strip().startswith("# "):
        return lines[0].strip().removeprefix("# ").strip() or None, "\n".join(lines[1:]).strip()
    return None, text.strip()


def manuscript_text(pages: list[dict[str, Any]]) -> str:
    return "\n\n".join(text for text in (blocks_text(page["blocks"]) for page in pages if not page["hidden"]) if text)


# -- reading ------------------------------------------------------------------------------------


def _word_count(pages: list[dict[str, Any]]) -> int:
    return sum(len(blocks_text(page["blocks"]).split()) for page in pages if not page["hidden"])


def _full_project(repository: PostgresStoryRepository, context: TenantContext, row: dict[str, Any]) -> StoryProject:
    pages = repository.pages(context, row["id"])
    return StoryProject.model_validate({
        **row,
        "page_count": sum(1 for page in pages if not page["hidden"]),
        "word_count": _word_count(pages),
        "pages": pages,
        "moves": repository.moves(context, row["id"]),
        "versions": repository.versions(context, row["id"]),
        "characters": repository.characters(context, row["id"]),
        "notes": repository.notes(context, row["id"]),
    })


def _require(repository: PostgresStoryRepository, context: TenantContext, project_id: str, *,
             lock: bool = False, live: bool = True) -> dict[str, Any]:
    row = repository.project(context, project_id, lock=lock)
    if row is None:
        raise StoryNotFound("story_project_not_found")
    if live and row["deleted_at"] is not None:
        raise StoryConflict("story_project_in_trash")
    return row


def list_projects(database: Any, context: TenantContext, *, trashed: bool = False) -> list[StoryProjectSummary]:
    with unit_of_work(database) as work:
        rows = PostgresStoryRepository(work.connection).projects(context, trashed=trashed)
        work.rollback()
    return [StoryProjectSummary.model_validate(row) for row in rows]


def get_project(database: Any, context: TenantContext, project_id: str) -> StoryProject:
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        project = _full_project(repository, context, _require(repository, context, project_id, live=False))
        work.rollback()
    return project


def get_version(database: Any, context: TenantContext, project_id: str, version_id: str) -> StoryVersion:
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, live=False)
        version = repository.version(context, project_id, version_id)
        work.rollback()
    if version is None:
        raise StoryNotFound("story_version_not_found")
    return StoryVersion.model_validate(version)


# -- writing ------------------------------------------------------------------------------------


def create_project(database: Any, context: TenantContext, request: StoryProjectCreate) -> StoryProject:
    project_id = new_id("story")
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        repository.create_project(context, {"id": project_id, **request.model_dump()})
        project = _full_project(repository, context, _require(repository, context, project_id))
        work.commit()
    return project


def update_project(database: Any, context: TenantContext, project_id: str, **values: Any) -> StoryProject:
    """Change a story's settings. Choosing a preset (ST-5.2) gives the story its tone and writing style."""
    values = {key: value for key, value in values.items() if value is not None}
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, lock=True)
        if values.get("preset_id"):
            preset = next((note for note in repository.notes(context, project_id)
                           if note["kind"] == "preset" and note["id"] == values["preset_id"]), None)
            if preset is None:
                raise StoryNotFound("story_preset_not_found")
            for key in ("tone", "writing_style"):
                if preset[key] and key not in values:
                    values[key] = preset[key]
        repository.update_project(context, project_id, **values)
        project = _full_project(repository, context, _require(repository, context, project_id))
        work.commit()
    return project


def set_trashed(database: Any, context: TenantContext, project_id: str, trashed: bool) -> StoryProject:
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, lock=True, live=False)
        repository.set_trashed(context, project_id, trashed)
        project = _full_project(repository, context, _require(repository, context, project_id, live=False))
        work.commit()
    return project


def purge_project(database: Any, context: TenantContext, project_id: str) -> None:
    """Delete a project for good; only one already in the trash."""
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, lock=True, live=False)
        if not repository.purge_project(context, project_id):
            raise StoryConflict("story_project_not_in_trash")
        work.commit()


def append_page(database: Any, context: TenantContext, project_id: str, *, blocks: list[dict[str, Any]],
                title: str = "", chapter: int | None = None) -> StoryProject:
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, lock=True)
        repository.append_page(context, project_id, {
            "id": new_id("page"), "chapter": chapter or max(1, repository.last_chapter(context, project_id)),
            "title": title, "blocks": blocks,
        })
        repository.touch_project(context, project_id)
        project = _full_project(repository, context, _require(repository, context, project_id))
        work.commit()
    return project


def update_page(database: Any, context: TenantContext, project_id: str, page_id: str, *,
                base_blocks: list[dict[str, Any]] | None = None, **values: Any) -> StoryProject:
    """A page's title or blocks as the writer edited them (ST-6.1).

    New blocks replace the page's only while it still holds ``base_blocks``, the blocks the writer started
    from, so an edit never overwrites a change accepted, restored or saved since it was opened.
    """
    values = {key: value for key, value in values.items() if value is not None and key in {"title", "blocks"}}
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, lock=True)
        if "blocks" in values:
            page = next((page for page in repository.pages(context, project_id) if page["id"] == page_id), None)
            if page is None:
                raise StoryNotFound("story_page_not_found")
            # The request's text is cleaned of control characters, so the stored text is compared cleaned.
            stored = [{**block, "text": CONTROL_CHARS.sub("", block.get("text") or "")} for block in page["blocks"]]
            if base_blocks is None or [_block_key(block) for block in stored] \
                    != [_block_key(block) for block in base_blocks]:
                raise StoryConflict("story_page_changed")
        if not repository.update_page(context, project_id, page_id, **values):
            raise StoryNotFound("story_page_not_found")
        repository.touch_project(context, project_id)
        project = _full_project(repository, context, _require(repository, context, project_id))
        work.commit()
    return project


def _snapshot(repository: PostgresStoryRepository, context: TenantContext, project_id: str) -> list[dict[str, Any]]:
    return [{"chapter": page["chapter"], "title": page["title"], "blocks": page["blocks"]}
            for page in repository.pages(context, project_id, include_hidden=False)]


def save_version(database: Any, context: TenantContext, project_id: str, *, title: str = "",
                 kind: str = "manual") -> StoryProject:
    """Keep the manuscript as it is now as a numbered version; ``kept_run`` keeps an interactive run (ST-3.6)."""
    if kind not in {"manual", "kept_run"}:
        raise ValueError(f"cannot save a {kind} version")
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, lock=True)
        pages = _snapshot(repository, context, project_id)
        if kind == "kept_run" and not pages:
            raise StoryConflict("story_has_no_pages")
        repository.add_version(context, project_id, {
            "id": new_id("version"), "kind": kind, "title": title, "pages": pages,
        })
        repository.touch_project(context, project_id)
        project = _full_project(repository, context, _require(repository, context, project_id))
        work.commit()
    return project


def undo_move(database: Any, context: TenantContext, project_id: str) -> StoryProject:
    """Take back the player's last move: its page is hidden and stays a branch that can be opened (ST-3.4)."""
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, lock=True)
        visible = repository.pages(context, project_id, include_hidden=False)
        moved = {move["page_id"] for move in repository.moves(context, project_id)}
        if not visible or visible[-1]["id"] not in moved:
            raise StoryConflict("story_no_move_to_undo")
        repository.update_page(context, project_id, visible[-1]["id"], hidden=True)
        repository.touch_project(context, project_id)
        project = _full_project(repository, context, _require(repository, context, project_id))
        work.commit()
    return project


def open_page(database: Any, context: TenantContext, project_id: str, page_id: str) -> StoryProject:
    """Make the run that ends at a page the story: go back to an earlier move or open a branch (ST-3.4).

    Nothing is deleted: the pages after it are hidden, and the next move from here starts a new branch.
    """
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, lock=True)
        if not repository.show_run_to(context, project_id, page_id):
            raise StoryNotFound("story_page_not_found")
        repository.touch_project(context, project_id)
        project = _full_project(repository, context, _require(repository, context, project_id))
        work.commit()
    return project


def restore_version(database: Any, context: TenantContext, project_id: str, version_id: str) -> StoryProject:
    """Make a version the manuscript. The manuscript it replaces is kept as a version first, so nothing is lost."""
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, lock=True)
        version = repository.version(context, project_id, version_id)
        if version is None:
            raise StoryNotFound("story_version_not_found")
        current = _snapshot(repository, context, project_id)
        if current:
            repository.add_version(context, project_id, {
                "id": new_id("version"), "kind": "manual",
                "title": f"Before restoring version {version['version_number']}", "pages": current,
            })
        repository.hide_visible_pages(context, project_id)
        for page in version["pages"] or []:
            repository.append_page(context, project_id, {
                "id": new_id("page"), "chapter": int(page.get("chapter") or 1), "title": page.get("title", ""),
                "blocks": page.get("blocks") or [],
            })
        repository.touch_project(context, project_id)
        project = _full_project(repository, context, _require(repository, context, project_id))
        work.commit()
    return project


def replace_characters(database: Any, context: TenantContext, project_id: str,
                       characters: list[dict[str, Any]]) -> StoryProject:
    ids = [character["id"] for character in characters]
    if len(ids) != len(set(ids)):
        raise StoryConflict("story_character_ids_repeat")
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, lock=True)
        repository.replace_characters(context, project_id, characters)
        repository.touch_project(context, project_id)
        project = _full_project(repository, context, _require(repository, context, project_id))
        work.commit()
    return project


def replace_notes(database: Any, context: TenantContext, project_id: str, notes: list[StoryNoteInput]) -> StoryProject:
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        project = _require(repository, context, project_id, lock=True)
        own = {note["id"] for note in repository.notes(context, project_id)}
        rows, seen = [], set()
        for note in notes:
            # An id this project doesn't have (or one repeated) is a new note.
            note_id = note.id if note.id in own and note.id not in seen else new_id("note")
            seen.add(note_id)
            rows.append({"id": note_id, "kind": note.kind, "title": note.title, "body": note.body,
                         "tone": note.tone, "writing_style": note.writing_style})
        repository.replace_notes(context, project_id, rows)
        # A preset that is gone (or is no longer a preset) is no longer the one the story is written with.
        if project["preset_id"] and not any(row["id"] == project["preset_id"] and row["kind"] == "preset"
                                            for row in rows):
            repository.update_project(context, project_id, preset_id="")
        repository.touch_project(context, project_id)
        project = _full_project(repository, context, _require(repository, context, project_id))
        work.commit()
    return project


# -- the plan (ST-5.1) --------------------------------------------------------------------------


def outline_beat(outline: list[dict[str, Any]], beat_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """The chapter of the outline that holds a beat, and the beat."""
    for chapter in outline or []:
        for beat in chapter.get("beats") or []:
            if beat.get("id") == beat_id:
                return chapter, beat
    return None


def _known_beats(outline: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {beat["id"]: beat for chapter in outline or [] for beat in chapter.get("beats") or [] if beat.get("id")}


def _outline_rows(chapters: list[dict[str, Any]], known: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Chapters numbered by their place; a beat the outline already has keeps its id and its page."""
    rows, seen = [], set()
    for number, chapter in enumerate(chapters, start=1):
        beats = []
        for beat in chapter.get("beats") or []:
            text = str(beat.get("text") or "").strip()
            if not text:
                continue
            beat_id = beat.get("id")
            beat_id = beat_id if beat_id in known and beat_id not in seen else new_id("beat")
            seen.add(beat_id)
            beats.append({"id": beat_id, "text": text, "page_id": (known.get(beat_id) or {}).get("page_id")})
        rows.append({"chapter": number, "title": str(chapter.get("title") or "").strip(), "beats": beats})
    return rows


def replace_outline(database: Any, context: TenantContext, project_id: str,
                    chapters: list[StoryOutlineChapterInput]) -> StoryProject:
    """The writer's edit of the plan, saved whole."""
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        project = _require(repository, context, project_id, lock=True)
        outline = _outline_rows([chapter.model_dump() for chapter in chapters], _known_beats(project["outline"]))
        repository.update_project(context, project_id, outline=outline)
        project = _full_project(repository, context, _require(repository, context, project_id))
        work.commit()
    return project


def record_outline(database: Any, context: TenantContext, *, project_id: str, job_id: str,
                   chapters: list[dict[str, Any]]) -> dict[str, Any]:
    """A planning job's outline becomes the story's plan, once: a retried job writes nothing again."""
    if not any(chapter.get("beats") for chapter in chapters):
        raise ValueError("a story outline needs at least one beat")
    ref = {"project_id": project_id, "outline_job_id": job_id}
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        project = _require(repository, context, project_id, lock=True)
        if project["outline_source_job_id"] == job_id:
            work.rollback()
            return ref
        repository.update_project(context, project_id, outline=_outline_rows(chapters, {}),
                                  outline_source_job_id=job_id)
        work.commit()
    return ref


# -- import (ST-1.4) ----------------------------------------------------------------------------


def import_items(database: Any, context: TenantContext, items: list[StoryImportItem]) -> StoryImportResult:
    """Make a project of each story the browser still holds; one already imported is found, not made again."""
    created, existing = [], []
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        for item in items:
            found = repository.project_by_origin(context, item.origin_kind, item.origin_ref)
            if found is not None:
                existing.append(found["id"])
                continue
            heading, body = split_title(item.text)
            project_id = new_id("story")
            if not repository.create_project(context, {
                "id": project_id, "title": item.title.strip() or heading or "Untitled story",
                "premise": item.premise.strip(), "mode": item.mode,
                "origin_kind": item.origin_kind, "origin_ref": item.origin_ref,
            }):
                found = repository.project_by_origin(context, item.origin_kind, item.origin_ref)
                existing.append(found["id"] if found else project_id)
                continue
            blocks = text_to_blocks(body)
            # A page holds at most BLOCKS_MAX blocks, as a page edit and a version read allow; a longer text
            # is imported as several pages.
            for start in range(0, len(blocks), BLOCKS_MAX):
                repository.append_page(context, project_id, {
                    "id": new_id("page"), "chapter": 1, "blocks": blocks[start:start + BLOCKS_MAX]})
            if item.characters:
                unique = {character.id: character.model_dump() for character in item.characters}
                repository.replace_characters(context, project_id, list(unique.values()))
            if item.trashed:
                repository.set_trashed(context, project_id, True)
            created.append(project_id)
        work.commit()
    return StoryImportResult(created=created, existing=existing)


# -- the story job (ST-1.3) ---------------------------------------------------------------------


def job_project(database: Any, context: TenantContext, *, project_id: str | None, job_id: str,
                premise: str, mode: str, tone: str | None, writing_style: str | None) -> dict[str, Any]:
    """The project a story job writes into, with its visible manuscript.

    A job queued before projects existed has no project_id: it gets one of its own, found again by
    ``origin_kind = 'job'`` when the job is retried, so a retry never makes a second project.
    """
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        written = repository.page_by_job(context, job_id) or repository.version_by_job(context, job_id)
        if project_id:
            # A retry of a job that already wrote its page reports it, even if the story went to the trash since.
            row = _require(repository, context, project_id, live=written is None)
        else:
            row = repository.project_by_origin(context, "job", job_id)
            if row is None:
                repository.create_project(context, {
                    "id": new_id("story"), "premise": premise, "mode": mode if mode in {"writing", "interactive"} else "writing",
                    "tone": tone or "", "writing_style": writing_style or "", "origin_kind": "job", "origin_ref": job_id,
                })
                row = repository.project_by_origin(context, "job", job_id)
        pages = repository.pages(context, row["id"], include_hidden=False)
        result = {"project": row, "text": manuscript_text(pages), "pages": pages, "page_count": len(pages),
                  "last_chapter": max((page["chapter"] for page in pages), default=0),
                  "characters": repository.characters(context, row["id"]),
                  "notes": repository.notes(context, row["id"]),
                  "written": written}
        work.commit()
    return result


def record_job_result(database: Any, context: TenantContext, *, project_id: str, job_id: str, action: str,
                      interaction_mode: str, title: str | None, pages: list[dict[str, Any]],
                      player_text: str | None, chosen_suggestion: str | None = None, chapter: int | None = None,
                      new_characters: list[dict[str, Any]] | None = None,
                      beat_id: str | None = None, selection: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write a story job's pages as a page (draft, continue, a player's move) or a version (ST-1.3, ST-1.6).

    ``pages`` holds one page for a page job and the reworked manuscript for a version; each page has
    ``blocks`` and may have ``title``, ``chapter`` and ``suggested_moves``. Characters the job proposed
    join the cast as suggestions (ST-2.3). A page drafted from a beat of the outline is linked to it
    (ST-5.1). A job that reworked a selection (ST-6.2) passes ``selection``: the page, the range, and the
    original and proposed blocks; its version waits for the writer to accept or reject the change.
    ``source_job_id`` is unique on pages and versions, so a retried job writes nothing twice.
    """
    if not pages or not all(page.get("blocks") for page in pages):
        raise ValueError("a story job result needs at least one page with text")
    heading = (pages[0].get("title") or "").strip() or None
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        project = _require(repository, context, project_id, lock=True, live=False)
        already = repository.page_by_job(context, job_id) or repository.version_by_job(context, job_id)
        if already is not None:
            work.rollback()
            return _job_ref(project_id, already)
        if action in VERSION_ACTIONS:
            first_chapter = min((page["chapter"] for page in repository.pages(context, project_id,
                                                                              include_hidden=False)), default=1)
            version_id = new_id("version")
            repository.add_version(context, project_id, {
                "id": version_id, "kind": action, "title": title or heading or project["title"],
                "source_job_id": job_id,
                "pages": [{"chapter": int(page.get("chapter") or first_chapter), "title": page.get("title") or "",
                           "blocks": page["blocks"]} for page in pages],
                "selection": {**selection, "status": "pending"} if selection is not None else None,
            })
            written = {"version_id": version_id}
        else:
            # A page goes at the end of the story: the chapter it continues, or the one the writer named.
            chapter = chapter or max(1, repository.last_chapter(context, project_id))
            page_id = new_id("page")
            repository.append_page(context, project_id, {
                "id": page_id, "chapter": chapter, "title": heading or "", "blocks": pages[0]["blocks"],
                "suggested_moves": pages[0].get("suggested_moves") or [], "source_job_id": job_id,
                "summary": pages[0].get("summary") or "",
            })
            if player_text:
                repository.add_move(context, project_id, {
                    "id": new_id("move"), "page_id": page_id, "player_text": player_text,
                    "chosen_suggestion": chosen_suggestion or "",
                    "parent_move_id": repository.last_move_id(context, project_id),
                })
            written = {"page_id": page_id}
            found = outline_beat(project["outline"], beat_id) if beat_id else None
            if found is not None:
                found[1]["page_id"] = page_id
                repository.update_project(context, project_id, outline=project["outline"])
            if not project["title"] and (heading or title):
                repository.update_project(context, project_id, title=heading or title)
        if new_characters:
            room = CHARACTERS_MAX - len(repository.characters(context, project_id))
            repository.suggest_characters(context, project_id, new_characters[:max(0, room)])
        repository.touch_project(context, project_id)
        work.commit()
    return {"project_id": project_id, **written}


def _block_key(block: dict[str, Any]) -> tuple[Any, ...]:
    return (block.get("kind") or "narration", block.get("text") or "", block.get("speaker_id") or None,
            block.get("attribution") or None)


def _pending_selection(repository: PostgresStoryRepository, context: TenantContext, project_id: str,
                       version_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    version = repository.version(context, project_id, version_id)
    if version is None:
        raise StoryNotFound("story_version_not_found")
    selection = version.get("selection")
    if not selection or selection.get("status") != "pending":
        raise StoryConflict("story_selection_not_pending")
    return version, selection


def accept_selection(database: Any, context: TenantContext, project_id: str, version_id: str) -> StoryProject:
    """Make a version's proposed selection change on its page (ST-6.2), keeping the manuscript before it.

    The change goes in only while the selected blocks are as they were when the job read them; a page
    edited, restored or removed since then is a conflict, and the writer asks again.
    """
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, lock=True)
        version, selection = _pending_selection(repository, context, project_id, version_id)
        page = next((page for page in repository.pages(context, project_id, include_hidden=False)
                     if page["id"] == selection["page_id"]), None)
        start, end = int(selection["start"]), int(selection["end"])
        if page is None or [_block_key(block) for block in page["blocks"][start:end]] != [
                _block_key(block) for block in selection["original"]]:
            raise StoryConflict("story_selection_page_changed")
        repository.add_version(context, project_id, {
            "id": new_id("version"), "kind": "manual",
            "title": f"Before accepting version {version['version_number']}",
            "pages": _snapshot(repository, context, project_id),
        })
        blocks = [*page["blocks"][:start], *selection["proposed"], *page["blocks"][end:]]
        repository.update_page(context, project_id, page["id"], blocks=blocks)
        repository.set_selection_status(context, project_id, version_id, "accepted")
        repository.touch_project(context, project_id)
        project = _full_project(repository, context, _require(repository, context, project_id))
        work.commit()
    return project


def reject_selection(database: Any, context: TenantContext, project_id: str, version_id: str) -> StoryProject:
    """Turn down a version's proposed selection change (ST-6.2); the manuscript stays as it is."""
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        _require(repository, context, project_id, lock=True)
        _pending_selection(repository, context, project_id, version_id)
        repository.set_selection_status(context, project_id, version_id, "rejected")
        repository.touch_project(context, project_id)
        project = _full_project(repository, context, _require(repository, context, project_id))
        work.commit()
    return project


def written_by_job(database: Any, context: TenantContext, project_id: str, job_id: str) -> dict[str, Any]:
    """What a job already wrote: its title, its text and where it went (for a retried job).

    The text is what the first attempt reported: a page under its own heading, a version's manuscript with
    no heading, and a selection version's proposed passage alone.
    """
    with unit_of_work(database) as work:
        repository = PostgresStoryRepository(work.connection)
        page = repository.page_by_job(context, job_id)
        if page is not None:
            title, content = page["title"], blocks_text(page["blocks"])
            content = f"# {title}\n\n{content}" if title else content
            ref = _job_ref(project_id, page)
        else:
            summary = repository.version_by_job(context, job_id)
            if summary is None:
                raise StoryNotFound("story_job_output_not_found")
            version = repository.version(context, project_id, summary["id"]) or {"pages": []}
            title = summary["title"]
            selection = version.get("selection")
            content = blocks_text(selection.get("proposed") or []) if isinstance(selection, dict) else \
                "\n\n".join(blocks_text(page.get("blocks") or []) for page in version["pages"] or [])
            ref = _job_ref(project_id, summary)
        work.rollback()
    return {"title": title, "content": content, "ref": ref}


def _job_ref(project_id: str, written: dict[str, Any]) -> dict[str, Any]:
    key = "page_id" if "position" in written else "version_id"
    return {"project_id": project_id, key: written["id"]}
