"""Every SQL statement of Dubbing, against its own tables only."""
from __future__ import annotations

import json
import uuid
from typing import Any

from app.persistence.tenant import TenantContext

_PROJECT_COLUMNS = ("id", "title", "source_asset_id", "source_language", "target_language", "translator", "engine",
                    "speakers", "duration_seconds", "steps", "assets", "casting", "created_at", "updated_at")
_SEGMENT_COLUMNS = ("id", "position", "source_key", "speaker", "start_seconds", "end_seconds", "source_text",
                    "translation", "translation_revision", "translation_origin", "voice_override", "take_asset_id",
                    "take_revision", "take_seconds", "fit_status", "fit_ratio", "shortenings", "approved_revision",
                    "approved_take_asset_id", "updated_at")
_JSON_FIELDS = ("steps", "assets", "casting")


def _row(columns: tuple[str, ...], row: Any) -> dict[str, Any]:
    value = dict(zip(columns, row))
    for key in ("created_at", "updated_at"):
        if key in value and value[key] is not None and not isinstance(value[key], str):
            value[key] = value[key].isoformat()
    return value


class PostgresDubbingRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    # -- projects -----------------------------------------------------------------------------

    def create_project(self, context: TenantContext, project: dict[str, Any]) -> None:
        self.connection.execute(
            """INSERT INTO omnix_dubbing_projects
                   (id, workspace_id, title, source_asset_id, source_language, target_language, translator,
                    engine, speakers)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (project["id"], context.workspace_id, project["title"], project["source_asset_id"],
             project["source_language"], project["target_language"], project.get("translator", ""),
             project.get("engine", ""), int(project.get("speakers", 0))),
        )

    def project(self, context: TenantContext, project_id: str, *, lock: bool = False) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {', '.join(_PROJECT_COLUMNS)} FROM omnix_dubbing_projects "
            f"WHERE workspace_id = %s AND id = %s{' FOR UPDATE' if lock else ''}",
            (context.workspace_id, project_id),
        ).fetchone()
        return _row(_PROJECT_COLUMNS, row) if row else None

    def projects(self, context: TenantContext) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"SELECT {', '.join(_PROJECT_COLUMNS)} FROM omnix_dubbing_projects WHERE workspace_id = %s "
            "ORDER BY updated_at DESC, id LIMIT 200",
            (context.workspace_id,),
        ).fetchall()
        return [_row(_PROJECT_COLUMNS, row) for row in rows]

    def update_project(self, context: TenantContext, project_id: str, **values: Any) -> bool:
        allowed = {"title", "source_language", "target_language", "translator", "engine", "speakers",
                   "duration_seconds", *_JSON_FIELDS}
        assignments, parameters = ["updated_at = clock_timestamp()"], []
        for key, value in values.items():
            if key not in allowed:
                raise ValueError(f"cannot update {key}")
            if key in _JSON_FIELDS:
                assignments.append(f"{key} = %s::jsonb")
                parameters.append(json.dumps(value))
            else:
                assignments.append(f"{key} = %s")
                parameters.append(value)
        cursor = self.connection.execute(
            f"UPDATE omnix_dubbing_projects SET {', '.join(assignments)} WHERE workspace_id = %s AND id = %s",
            (*parameters, context.workspace_id, project_id),
        )
        return cursor.rowcount == 1

    def delete_project(self, context: TenantContext, project_id: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM omnix_dubbing_projects WHERE workspace_id = %s AND id = %s",
            (context.workspace_id, project_id),
        )
        return cursor.rowcount == 1

    # -- segments -----------------------------------------------------------------------------

    def segments(self, context: TenantContext, project_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"SELECT {', '.join(_SEGMENT_COLUMNS)} FROM omnix_dubbing_segments "
            "WHERE workspace_id = %s AND project_id = %s ORDER BY position, id",
            (context.workspace_id, project_id),
        ).fetchall()
        return [_row(_SEGMENT_COLUMNS, row) for row in rows]

    def replace_segments(self, context: TenantContext, project_id: str, lines: list[dict[str, Any]]) -> dict[str, int]:
        """The transcript's lines, keeping every line whose identity (``source_key``) is unchanged."""
        existing = {row[0]: row[1] for row in self.connection.execute(
            "SELECT source_key, id FROM omnix_dubbing_segments WHERE workspace_id = %s AND project_id = %s",
            (context.workspace_id, project_id),
        ).fetchall()}
        kept = 0
        wanted = {line["source_key"] for line in lines}
        removed = [key for key in existing if key not in wanted]
        if removed:
            self.connection.execute(
                "DELETE FROM omnix_dubbing_segments WHERE workspace_id = %s AND project_id = %s AND source_key = ANY(%s)",
                (context.workspace_id, project_id, removed),
            )
        for position, line in enumerate(lines):
            if line["source_key"] in existing:
                kept += 1
                self.connection.execute(
                    """UPDATE omnix_dubbing_segments SET position = %s, updated_at = clock_timestamp()
                        WHERE workspace_id = %s AND project_id = %s AND source_key = %s""",
                    (position, context.workspace_id, project_id, line["source_key"]),
                )
                continue
            self.connection.execute(
                """INSERT INTO omnix_dubbing_segments
                       (id, workspace_id, project_id, position, source_key, speaker, start_seconds, end_seconds, source_text)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (f"dubline:{uuid.uuid4().hex}", context.workspace_id, project_id, position, line["source_key"],
                 line["speaker"], line["start_seconds"], line["end_seconds"], line["source_text"]),
            )
        return {"kept": kept, "added": len(lines) - kept, "removed": len(removed)}

    def set_translation(self, context: TenantContext, project_id: str, segment_id: str, text: str, origin: str, *,
                        expected_revision: int | None = None, replace_person: bool = False) -> bool:
        """New words bump the revision (so earlier takes and approvals no longer count); the same words do not.

        With ``expected_revision`` (a machine rewrite, such as shortening or translation) the words change
        only while the line is still at that revision and, unless ``replace_person`` (the person asked for
        this line again), a person has not written them.
        """
        cursor = self.connection.execute(
            """UPDATE omnix_dubbing_segments
                  SET translation = %s, translation_origin = %s,
                      translation_revision = translation_revision + 1, updated_at = clock_timestamp()
                WHERE workspace_id = %s AND project_id = %s AND id = %s AND translation IS DISTINCT FROM %s
                  AND (%s::integer IS NULL
                       OR (translation_revision = %s::integer
                           AND (%s OR translation_origin IS DISTINCT FROM 'person')))""",
            (text, origin, context.workspace_id, project_id, segment_id, text, expected_revision, expected_revision,
             replace_person),
        )
        return cursor.rowcount == 1

    def set_take(self, context: TenantContext, project_id: str, segment_id: str, *, asset_id: str, revision: int,
                 seconds: float, fit_status: str, fit_ratio: float, shortenings: int) -> bool:
        cursor = self.connection.execute(
            """UPDATE omnix_dubbing_segments
                  SET take_asset_id = %s, take_revision = %s, take_seconds = %s, fit_status = %s, fit_ratio = %s,
                      shortenings = %s, updated_at = clock_timestamp()
                WHERE workspace_id = %s AND project_id = %s AND id = %s""",
            (asset_id, revision, seconds, fit_status, fit_ratio, shortenings, context.workspace_id, project_id,
             segment_id),
        )
        return cursor.rowcount == 1

    def set_voice_override(self, context: TenantContext, project_id: str, segment_id: str, voice_id: str) -> bool:
        cursor = self.connection.execute(
            """UPDATE omnix_dubbing_segments SET voice_override = %s, updated_at = clock_timestamp()
                WHERE workspace_id = %s AND project_id = %s AND id = %s""",
            (voice_id, context.workspace_id, project_id, segment_id),
        )
        return cursor.rowcount == 1

    def approve(self, context: TenantContext, project_id: str, segment_ids: list[str]) -> int:
        """Approve lines whose take was rendered from their current words; returns how many."""
        cursor = self.connection.execute(
            """UPDATE omnix_dubbing_segments
                  SET approved_revision = translation_revision, approved_take_asset_id = take_asset_id,
                      updated_at = clock_timestamp()
                WHERE workspace_id = %s AND project_id = %s AND id = ANY(%s)
                  AND take_asset_id <> '' AND take_revision = translation_revision AND translation <> ''""",
            (context.workspace_id, project_id, segment_ids),
        )
        return cursor.rowcount

    def unapprove(self, context: TenantContext, project_id: str, segment_ids: list[str]) -> int:
        cursor = self.connection.execute(
            """UPDATE omnix_dubbing_segments SET approved_revision = NULL, approved_take_asset_id = NULL,
                      updated_at = clock_timestamp()
                WHERE workspace_id = %s AND project_id = %s AND id = ANY(%s)""",
            (context.workspace_id, project_id, segment_ids),
        )
        return cursor.rowcount
