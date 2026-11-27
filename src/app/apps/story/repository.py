"""Every SQL statement of the storyteller's projects, against its own tables only (ST-1.1, ST-1.2)."""
from __future__ import annotations

import json
from typing import Any

from app.persistence.tenant import TenantContext

_PROJECT_COLUMNS = ("id", "title", "premise", "mode", "tone", "writing_style", "read_settings", "origin_kind",
                    "origin_ref", "outline", "outline_source_job_id", "preset_id", "deleted_at", "created_at",
                    "updated_at")
_PAGE_COLUMNS = ("id", "chapter", "position", "title", "blocks", "suggested_moves", "hidden", "source_job_id",
                 "parent_page_id", "summary", "created_at")
_MOVE_COLUMNS = ("id", "page_id", "player_text", "chosen_suggestion", "parent_move_id", "created_at")
_VERSION_COLUMNS = ("id", "version_number", "kind", "title", "source_job_id", "created_at", "selection")
_CHARACTER_COLUMNS = ("id", "name", "aliases", "description", "traits", "role", "suggested")
_NOTE_COLUMNS = ("id", "kind", "title", "body", "tone", "writing_style", "created_at", "updated_at")
#: Project columns stored as JSONB.
_PROJECT_JSON = frozenset({"read_settings", "outline"})
_TIMES = ("created_at", "updated_at", "deleted_at")


def _row(columns: tuple[str, ...], row: Any) -> dict[str, Any]:
    value = dict(zip(columns, row))
    for key in _TIMES:
        if key in value and value[key] is not None and not isinstance(value[key], str):
            value[key] = value[key].isoformat()
    return value


def _select(columns: tuple[str, ...]) -> str:
    return ", ".join(columns)


class PostgresStoryRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    # -- projects -----------------------------------------------------------------------------

    def create_project(self, context: TenantContext, project: dict[str, Any]) -> bool:
        """Insert a project; False when its origin is already a project (an import or a job run again)."""
        row = self.connection.execute(
            """INSERT INTO omnix_story_projects
                   (id, workspace_id, title, premise, mode, tone, writing_style, read_settings, origin_kind, origin_ref)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
               ON CONFLICT (workspace_id, origin_kind, origin_ref) WHERE origin_ref <> '' DO NOTHING
               RETURNING id""",
            (project["id"], context.workspace_id, project.get("title", ""), project.get("premise", ""),
             project.get("mode", "writing"), project.get("tone", ""), project.get("writing_style", ""),
             json.dumps(project.get("read_settings") or {}), project.get("origin_kind", "new"),
             project.get("origin_ref", "")),
        ).fetchone()
        return row is not None

    def project_by_origin(self, context: TenantContext, origin_kind: str, origin_ref: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {_select(_PROJECT_COLUMNS)} FROM omnix_story_projects "
            "WHERE workspace_id = %s AND origin_kind = %s AND origin_ref = %s",
            (context.workspace_id, origin_kind, origin_ref),
        ).fetchone()
        return _row(_PROJECT_COLUMNS, row) if row else None

    def project(self, context: TenantContext, project_id: str, *, lock: bool = False) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {_select(_PROJECT_COLUMNS)} FROM omnix_story_projects "
            f"WHERE workspace_id = %s AND id = %s{' FOR UPDATE' if lock else ''}",
            (context.workspace_id, project_id),
        ).fetchone()
        return _row(_PROJECT_COLUMNS, row) if row else None

    def projects(self, context: TenantContext, *, trashed: bool) -> list[dict[str, Any]]:
        """The whole library, newest first: one summary row per story, never cut short."""
        rows = self.connection.execute(
            f"""SELECT {', '.join('project.' + column for column in _PROJECT_COLUMNS)},
                       (SELECT count(*) FROM omnix_story_pages AS page
                         WHERE page.workspace_id = project.workspace_id AND page.project_id = project.id
                           AND NOT page.hidden) AS page_count,
                       (SELECT coalesce(sum(array_length(regexp_split_to_array(trim(block.value ->> 'text'), '\\s+'), 1)), 0)
                          FROM omnix_story_pages AS page, jsonb_array_elements(page.blocks) AS block
                         WHERE page.workspace_id = project.workspace_id AND page.project_id = project.id
                           AND NOT page.hidden AND trim(block.value ->> 'text') <> '') AS word_count
                  FROM omnix_story_projects AS project
                 WHERE project.workspace_id = %s AND (project.deleted_at IS NOT NULL) = %s
                 ORDER BY project.updated_at DESC, project.id""",
            (context.workspace_id, trashed),
        ).fetchall()
        projects = []
        for row in rows:
            project = _row(_PROJECT_COLUMNS, row[: len(_PROJECT_COLUMNS)])
            project["page_count"], project["word_count"] = int(row[-2]), int(row[-1])
            projects.append(project)
        return projects

    def update_project(self, context: TenantContext, project_id: str, **values: Any) -> bool:
        allowed = {"title", "premise", "mode", "tone", "writing_style", "read_settings", "outline",
                   "outline_source_job_id", "preset_id"}
        assignments, parameters = ["updated_at = clock_timestamp()"], []
        for key, value in values.items():
            if key not in allowed:
                raise ValueError(f"cannot update {key}")
            if key in _PROJECT_JSON:
                assignments.append(f"{key} = %s::jsonb")
                parameters.append(json.dumps(value))
            else:
                assignments.append(f"{key} = %s")
                parameters.append(value)
        return bool(self.connection.execute(
            f"UPDATE omnix_story_projects SET {', '.join(assignments)} WHERE workspace_id = %s AND id = %s",
            (*parameters, context.workspace_id, project_id),
        ).rowcount)

    def touch_project(self, context: TenantContext, project_id: str) -> None:
        self.connection.execute(
            "UPDATE omnix_story_projects SET updated_at = clock_timestamp() WHERE workspace_id = %s AND id = %s",
            (context.workspace_id, project_id),
        )

    def set_trashed(self, context: TenantContext, project_id: str, trashed: bool) -> bool:
        return bool(self.connection.execute(
            "UPDATE omnix_story_projects SET deleted_at = CASE WHEN %s THEN clock_timestamp() END, "
            "updated_at = clock_timestamp() WHERE workspace_id = %s AND id = %s",
            (trashed, context.workspace_id, project_id),
        ).rowcount)

    def purge_project(self, context: TenantContext, project_id: str) -> bool:
        """Delete a trashed project and, by cascade, everything of it."""
        return bool(self.connection.execute(
            "DELETE FROM omnix_story_projects WHERE workspace_id = %s AND id = %s AND deleted_at IS NOT NULL",
            (context.workspace_id, project_id),
        ).rowcount)

    # -- pages and moves ------------------------------------------------------------------------

    def pages(self, context: TenantContext, project_id: str, *, include_hidden: bool = True) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"SELECT {_select(_PAGE_COLUMNS)} FROM omnix_story_pages WHERE workspace_id = %s AND project_id = %s"
            f"{'' if include_hidden else ' AND NOT hidden'} ORDER BY chapter, position, created_at, id",
            (context.workspace_id, project_id),
        ).fetchall()
        return [_row(_PAGE_COLUMNS, row) for row in rows]

    def page_by_job(self, context: TenantContext, job_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {_select(_PAGE_COLUMNS)}, project_id FROM omnix_story_pages "
            "WHERE workspace_id = %s AND source_job_id = %s",
            (context.workspace_id, job_id),
        ).fetchone()
        if not row:
            return None
        page = _row(_PAGE_COLUMNS, row[:-1])
        page["project_id"] = row[-1]
        return page

    def append_page(self, context: TenantContext, project_id: str, page: dict[str, Any]) -> bool:
        """Append a page at the end of its chapter; False when its job already wrote it.

        The page continues from the story's last visible page, its parent (ST-3.4).
        """
        row = self.connection.execute(
            """INSERT INTO omnix_story_pages
                   (id, workspace_id, project_id, chapter, position, title, blocks, suggested_moves, source_job_id,
                    parent_page_id, summary)
               SELECT %s, %s, %s, %s,
                      coalesce((SELECT max(position) + 1 FROM omnix_story_pages
                                 WHERE workspace_id = %s AND project_id = %s AND chapter = %s), 0),
                      %s, %s::jsonb, %s::jsonb, %s,
                      (SELECT id FROM omnix_story_pages WHERE workspace_id = %s AND project_id = %s AND NOT hidden
                        ORDER BY chapter DESC, position DESC, created_at DESC, id DESC LIMIT 1),
                      %s
               ON CONFLICT (source_job_id) DO NOTHING
               RETURNING id""",
            (page["id"], context.workspace_id, project_id, int(page["chapter"]),
             context.workspace_id, project_id, int(page["chapter"]),
             page.get("title", ""), json.dumps(page["blocks"]), json.dumps(page.get("suggested_moves") or []),
             page.get("source_job_id"), context.workspace_id, project_id, page.get("summary") or ""),
        ).fetchone()
        return row is not None

    def last_chapter(self, context: TenantContext, project_id: str) -> int:
        row = self.connection.execute(
            "SELECT max(chapter) FROM omnix_story_pages WHERE workspace_id = %s AND project_id = %s AND NOT hidden",
            (context.workspace_id, project_id),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def update_page(self, context: TenantContext, project_id: str, page_id: str, **values: Any) -> bool:
        assignments, parameters = [], []
        for key, value in values.items():
            if key == "blocks":
                assignments.append("blocks = %s::jsonb")
                parameters.append(json.dumps(value))
            elif key in {"title", "hidden"}:
                assignments.append(f"{key} = %s")
                parameters.append(value)
            else:
                raise ValueError(f"cannot update {key}")
        if not assignments:
            return self.page_exists(context, project_id, page_id)
        return bool(self.connection.execute(
            f"UPDATE omnix_story_pages SET {', '.join(assignments)} "
            "WHERE workspace_id = %s AND project_id = %s AND id = %s",
            (*parameters, context.workspace_id, project_id, page_id),
        ).rowcount)

    def page_exists(self, context: TenantContext, project_id: str, page_id: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM omnix_story_pages WHERE workspace_id = %s AND project_id = %s AND id = %s",
            (context.workspace_id, project_id, page_id),
        ).fetchone() is not None

    def hide_visible_pages(self, context: TenantContext, project_id: str) -> None:
        self.connection.execute(
            "UPDATE omnix_story_pages SET hidden = TRUE WHERE workspace_id = %s AND project_id = %s AND NOT hidden",
            (context.workspace_id, project_id),
        )

    def show_run_to(self, context: TenantContext, project_id: str, page_id: str) -> bool:
        """Make the chain of parents that ends at ``page_id`` the visible run; every other page is hidden."""
        return bool(self.connection.execute(
            """WITH RECURSIVE run AS (
                   SELECT id, parent_page_id FROM omnix_story_pages
                    WHERE workspace_id = %s AND project_id = %s AND id = %s
                   UNION
                   SELECT page.id, page.parent_page_id FROM omnix_story_pages AS page
                     JOIN run ON page.id = run.parent_page_id
                    WHERE page.workspace_id = %s AND page.project_id = %s
               )
               UPDATE omnix_story_pages SET hidden = (id NOT IN (SELECT id FROM run))
                WHERE workspace_id = %s AND project_id = %s AND EXISTS (SELECT 1 FROM run)""",
            (context.workspace_id, project_id, page_id, context.workspace_id, project_id,
             context.workspace_id, project_id),
        ).rowcount)

    def add_move(self, context: TenantContext, project_id: str, move: dict[str, Any]) -> None:
        self.connection.execute(
            """INSERT INTO omnix_story_moves
                   (id, workspace_id, project_id, page_id, player_text, chosen_suggestion, parent_move_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (move["id"], context.workspace_id, project_id, move.get("page_id"), move["player_text"],
             move.get("chosen_suggestion", ""), move.get("parent_move_id")),
        )

    def moves(self, context: TenantContext, project_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"SELECT {_select(_MOVE_COLUMNS)} FROM omnix_story_moves WHERE workspace_id = %s AND project_id = %s "
            "ORDER BY created_at, id",
            (context.workspace_id, project_id),
        ).fetchall()
        return [_row(_MOVE_COLUMNS, row) for row in rows]

    def last_move_id(self, context: TenantContext, project_id: str) -> str | None:
        row = self.connection.execute(
            """SELECT move.id FROM omnix_story_moves AS move
                 JOIN omnix_story_pages AS page ON page.workspace_id = move.workspace_id AND page.id = move.page_id
                WHERE move.workspace_id = %s AND move.project_id = %s AND NOT page.hidden
                ORDER BY move.created_at DESC, move.id DESC LIMIT 1""",
            (context.workspace_id, project_id),
        ).fetchone()
        return str(row[0]) if row else None

    # -- versions -----------------------------------------------------------------------------

    def versions(self, context: TenantContext, project_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"SELECT {_select(_VERSION_COLUMNS)} FROM omnix_story_versions WHERE workspace_id = %s AND project_id = %s "
            "ORDER BY version_number",
            (context.workspace_id, project_id),
        ).fetchall()
        return [_row(_VERSION_COLUMNS, row) for row in rows]

    def version(self, context: TenantContext, project_id: str, version_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {_select(_VERSION_COLUMNS)}, pages FROM omnix_story_versions "
            "WHERE workspace_id = %s AND project_id = %s AND id = %s",
            (context.workspace_id, project_id, version_id),
        ).fetchone()
        if not row:
            return None
        version = _row(_VERSION_COLUMNS, row[:-1])
        version["pages"] = row[-1]
        return version

    def version_by_job(self, context: TenantContext, job_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {_select(_VERSION_COLUMNS)}, project_id FROM omnix_story_versions "
            "WHERE workspace_id = %s AND source_job_id = %s",
            (context.workspace_id, job_id),
        ).fetchone()
        if not row:
            return None
        version = _row(_VERSION_COLUMNS, row[:-1])
        version["project_id"] = row[-1]
        return version

    def add_version(self, context: TenantContext, project_id: str, version: dict[str, Any]) -> bool:
        """Number and store a version; False when its job already stored it.

        The caller holds the project's row lock, so two versions never take the same number.
        """
        row = self.connection.execute(
            """INSERT INTO omnix_story_versions
                   (id, workspace_id, project_id, version_number, kind, title, pages, source_job_id, selection)
               SELECT %s, %s, %s,
                      coalesce((SELECT max(version_number) + 1 FROM omnix_story_versions
                                 WHERE workspace_id = %s AND project_id = %s), 1),
                      %s, %s, %s::jsonb, %s, %s::jsonb
               ON CONFLICT (source_job_id) DO NOTHING
               RETURNING id""",
            (version["id"], context.workspace_id, project_id, context.workspace_id, project_id,
             version["kind"], version.get("title", ""), json.dumps(version["pages"]), version.get("source_job_id"),
             json.dumps(version["selection"]) if version.get("selection") is not None else None),
        ).fetchone()
        return row is not None

    def set_selection_status(self, context: TenantContext, project_id: str, version_id: str, status: str) -> None:
        """Mark a version's proposed selection change accepted or rejected (ST-6.2)."""
        self.connection.execute(
            "UPDATE omnix_story_versions SET selection = jsonb_set(selection, '{status}', to_jsonb(%s::text)) "
            "WHERE workspace_id = %s AND project_id = %s AND id = %s AND selection IS NOT NULL",
            (status, context.workspace_id, project_id, version_id),
        )

    # -- cast and notes -------------------------------------------------------------------------

    def characters(self, context: TenantContext, project_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"SELECT {_select(_CHARACTER_COLUMNS)} FROM omnix_story_characters "
            "WHERE workspace_id = %s AND project_id = %s ORDER BY created_at, id",
            (context.workspace_id, project_id),
        ).fetchall()
        return [_row(_CHARACTER_COLUMNS, row) for row in rows]

    def replace_characters(self, context: TenantContext, project_id: str, characters: list[dict[str, Any]]) -> None:
        keep = [character["id"] for character in characters]
        self.connection.execute(
            "DELETE FROM omnix_story_characters WHERE workspace_id = %s AND project_id = %s AND NOT (id = ANY(%s))",
            (context.workspace_id, project_id, keep),
        )
        for character in characters:
            self.connection.execute(
                """INSERT INTO omnix_story_characters
                       (workspace_id, project_id, id, name, aliases, description, traits, role, suggested)
                   VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s)
                   ON CONFLICT (workspace_id, project_id, id) DO UPDATE
                      SET name = EXCLUDED.name, aliases = EXCLUDED.aliases, description = EXCLUDED.description,
                          traits = EXCLUDED.traits, role = EXCLUDED.role, suggested = EXCLUDED.suggested,
                          updated_at = clock_timestamp()""",
                (context.workspace_id, project_id, character["id"], character["name"],
                 json.dumps(character.get("aliases") or []), character.get("description", ""),
                 json.dumps(character.get("traits") or []), character.get("role", ""),
                 bool(character.get("suggested"))),
            )

    def suggest_characters(self, context: TenantContext, project_id: str, characters: list[dict[str, Any]]) -> None:
        """Add characters a page proposed, as suggestions; one the project already has is left as it is."""
        for character in characters:
            self.connection.execute(
                """INSERT INTO omnix_story_characters
                       (workspace_id, project_id, id, name, description, suggested)
                   VALUES (%s, %s, %s, %s, %s, TRUE)
                   ON CONFLICT (workspace_id, project_id, id) DO NOTHING""",
                (context.workspace_id, project_id, character["id"], character["name"],
                 character.get("description", "")),
            )

    def notes(self, context: TenantContext, project_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"SELECT {_select(_NOTE_COLUMNS)} FROM omnix_story_notes WHERE workspace_id = %s AND project_id = %s "
            "ORDER BY kind, created_at, id",
            (context.workspace_id, project_id),
        ).fetchall()
        return [_row(_NOTE_COLUMNS, row) for row in rows]

    def replace_notes(self, context: TenantContext, project_id: str, notes: list[dict[str, Any]]) -> None:
        keep = [note["id"] for note in notes]
        self.connection.execute(
            "DELETE FROM omnix_story_notes WHERE workspace_id = %s AND project_id = %s AND NOT (id = ANY(%s))",
            (context.workspace_id, project_id, keep),
        )
        for note in notes:
            # A note id from another project is not taken over: the conflict update only matches this project.
            self.connection.execute(
                """INSERT INTO omnix_story_notes (id, workspace_id, project_id, kind, title, body, tone, writing_style)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE
                      SET kind = EXCLUDED.kind, title = EXCLUDED.title, body = EXCLUDED.body, tone = EXCLUDED.tone,
                          writing_style = EXCLUDED.writing_style, updated_at = clock_timestamp()
                    WHERE omnix_story_notes.workspace_id = EXCLUDED.workspace_id
                      AND omnix_story_notes.project_id = EXCLUDED.project_id""",
                (note["id"], context.workspace_id, project_id, note["kind"], note.get("title", ""),
                 note.get("body", ""), note.get("tone", ""), note.get("writing_style", "")),
            )

    # -- voices (ST-4.2) --------------------------------------------------------------------------

    def voice_cast(self, context: TenantContext, project_id: str) -> dict[str, dict[str, str]]:
        rows = self.connection.execute(
            "SELECT speaker_id, voice_id, voice_revision, chosen_by FROM omnix_story_voice_cast "
            "WHERE workspace_id = %s AND project_id = %s",
            (context.workspace_id, project_id),
        ).fetchall()
        return {str(row[0]): {"voice_id": str(row[1]), "voice_revision": str(row[2]), "chosen_by": str(row[3])}
                for row in rows}

    def put_voice(self, context: TenantContext, project_id: str, speaker_id: str, *, voice_id: str,
                  voice_revision: str, chosen_by: str, replace: bool = False) -> None:
        """A speaker's voice. An automatic cast never replaces the writer's choice, unless ``replace`` (the stored
        voice is no longer castable, or its recording changed)."""
        self.connection.execute(
            """INSERT INTO omnix_story_voice_cast (workspace_id, project_id, speaker_id, voice_id, voice_revision,
                                                   chosen_by)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (workspace_id, project_id, speaker_id) DO UPDATE
                  SET voice_id = EXCLUDED.voice_id, voice_revision = EXCLUDED.voice_revision,
                      chosen_by = EXCLUDED.chosen_by, updated_at = clock_timestamp()
                WHERE %s OR EXCLUDED.chosen_by = 'writer' OR omnix_story_voice_cast.chosen_by = 'auto'""",
            (context.workspace_id, project_id, speaker_id, voice_id, voice_revision, chosen_by, bool(replace)),
        )

    def speech_audio(self, context: TenantContext, project_id: str, render_key: str) -> bytes | None:
        row = self.connection.execute(
            "SELECT audio FROM omnix_story_speech_audio WHERE workspace_id = %s AND project_id = %s AND render_key = %s",
            (context.workspace_id, project_id, render_key),
        ).fetchone()
        return bytes(row[0]) if row else None

    def put_speech_audio(self, context: TenantContext, project_id: str, render_key: str, *, page_id: str,
                         voice_id: str, audio: bytes) -> None:
        self.connection.execute(
            """INSERT INTO omnix_story_speech_audio (workspace_id, project_id, render_key, page_id, voice_id, audio)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (workspace_id, project_id, render_key) DO NOTHING""",
            (context.workspace_id, project_id, render_key, page_id, voice_id, audio),
        )


def delete_trashed_projects(connection: Any, retention_days: int, batch_size: int) -> int:
    """Projects in the trash longer than the retention period go, with every row of theirs (ST-1.5)."""
    return int(connection.execute(
        """
        DELETE FROM omnix_story_projects
         WHERE id IN (
             SELECT id
               FROM omnix_story_projects
              WHERE deleted_at IS NOT NULL
                AND deleted_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
              ORDER BY deleted_at, id
              LIMIT %s
         )
        """,
        (max(1, int(retention_days)), max(1, int(batch_size))),
    ).rowcount)
