"""Saved Voice Studio scripts, their lines and every take (Phase 1 §5).

A saved script gives each line a stable identity, so one line can be rendered
again without re-rendering the script, and every take is kept: a line points at
its selected take, and ``voice.restitch`` rebuilds the full render from the
selected takes. Rows are workspace-scoped (``tenant_isolation``); every query
also names the workspace, so a missing session scope never widens a read.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import current_tenant

from .script import parse_script


class ScriptNotFound(KeyError):
    pass


class ScriptRevisionConflict(RuntimeError):
    """The script changed since the caller read it."""


def _workspace() -> str:
    return current_tenant().workspace_id


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _script_row(row: Any) -> dict[str, Any]:
    return {
        "id": row[0], "title": row[1], "text": row[2], "engine": row[3],
        "settings": row[4] or {}, "revision": int(row[5]),
        "created_at": row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
        "updated_at": row[7].isoformat() if hasattr(row[7], "isoformat") else str(row[7]),
    }


def _line_row(row: Any) -> dict[str, Any]:
    return {
        "id": row[0], "position": int(row[1]), "speaker": row[2], "text": row[3],
        "pause_before_ms": row[4], "delivery_instruction": row[5] or "", "voice_id": row[6] or "",
        "selected_take_id": row[7] or "",
    }


def _take_row(row: Any) -> dict[str, Any]:
    return {
        "id": row[0], "line_id": row[1], "asset_id": row[2], "job_id": row[3] or "", "engine": row[4] or "",
        "text_hash": row[5], "duration": float(row[6] or 0.0), "pinned": bool(row[7]),
        "created_at": row[8].isoformat() if hasattr(row[8], "isoformat") else str(row[8]),
    }


_SCRIPT_COLUMNS = "id, title, text, engine, settings, revision, created_at, updated_at"
_LINE_COLUMNS = "id, position, speaker, text, pause_before_ms, delivery_instruction, voice_id, selected_take_id"
_TAKE_COLUMNS = "id, line_id, asset_id, job_id, engine, text_hash, duration_seconds, pinned, created_at"


def _sync_lines(connection: Any, workspace: str, script_id: str, text: str, casting: dict[str, Any]) -> None:
    """Make the script's lines match its text: unchanged lines keep their id and takes."""
    existing = connection.execute(
        f"SELECT {_LINE_COLUMNS} FROM omnix_voice_script_lines WHERE workspace_id = %s AND script_id = %s ORDER BY position",
        (workspace, script_id),
    ).fetchall()
    # A line keeps its identity when the same speaker says the same words, wherever it moved.
    available: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in existing:
        line = _line_row(row)
        available.setdefault((line["speaker"], line["text"]), []).append(line)
    kept: set[str] = set()
    for position, segment in enumerate(parse_script(text)):
        speaker, words = str(segment["speaker"]), str(segment["text"])
        cast = casting.get(speaker.casefold(), {}) if isinstance(casting, dict) else {}
        voice_id = str(cast.get("voice_id") or "")
        instruction = str(segment.get("delivery_instruction") or cast.get("delivery_instruction") or "")[:500]
        pause = segment.get("pause_before_ms")
        matches = available.get((speaker, words)) or []
        if matches:
            line = matches.pop(0)
            kept.add(line["id"])
            connection.execute(
                """UPDATE omnix_voice_script_lines
                      SET position = %s, pause_before_ms = %s, delivery_instruction = %s, voice_id = %s
                    WHERE workspace_id = %s AND id = %s""",
                (position, pause, instruction, voice_id, workspace, line["id"]),
            )
        else:
            line_id = f"vline:{uuid.uuid4().hex}"
            kept.add(line_id)
            connection.execute(
                """INSERT INTO omnix_voice_script_lines
                       (id, workspace_id, script_id, position, speaker, text, pause_before_ms,
                        delivery_instruction, voice_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (line_id, workspace, script_id, position, speaker, words, pause, instruction, voice_id),
            )
    stale = [str(row[0]) for row in existing if str(row[0]) not in kept]
    if stale:
        # Takes of removed lines go with them; their audio assets stay in the library.
        connection.execute(
            "DELETE FROM omnix_voice_takes WHERE workspace_id = %s AND line_id = ANY(%s)", (workspace, stale))
        connection.execute(
            "DELETE FROM omnix_voice_script_lines WHERE workspace_id = %s AND id = ANY(%s)", (workspace, stale))


def save_script(
    *, title: str, text: str, engine: str = "", settings: dict[str, Any] | None = None,
    casting: dict[str, Any] | None = None, script_id: str | None = None, expected_revision: int | None = None,
) -> dict[str, Any]:
    """Create or update a script and its lines; returns the script with its lines."""
    workspace = _workspace()
    settings_json = json.dumps(settings or {}, sort_keys=True)
    with unit_of_work() as work:
        connection = work.connection
        if script_id:
            row = connection.execute(
                f"SELECT {_SCRIPT_COLUMNS} FROM omnix_voice_scripts WHERE workspace_id = %s AND id = %s FOR UPDATE",
                (workspace, script_id),
            ).fetchone()
            if row is None:
                raise ScriptNotFound(script_id)
            if expected_revision is not None and int(row[5]) != int(expected_revision):
                raise ScriptRevisionConflict(f"script {script_id} is at revision {row[5]}, not {expected_revision}")
            connection.execute(
                """UPDATE omnix_voice_scripts
                      SET title = %s, text = %s, engine = %s, settings = %s::jsonb,
                          revision = revision + 1, updated_at = clock_timestamp()
                    WHERE workspace_id = %s AND id = %s""",
                (title, text, engine, settings_json, workspace, script_id),
            )
        else:
            script_id = f"vscript:{uuid.uuid4().hex}"
            connection.execute(
                """INSERT INTO omnix_voice_scripts (id, workspace_id, title, text, engine, settings)
                   VALUES (%s, %s, %s, %s, %s, %s::jsonb)""",
                (script_id, workspace, title, text, engine, settings_json),
            )
        _sync_lines(connection, workspace, script_id, text, casting or {})
        work.commit()
    return get_script(script_id)


def get_script(script_id: str) -> dict[str, Any]:
    workspace = _workspace()
    with unit_of_work() as work:
        connection = work.connection
        row = connection.execute(
            f"SELECT {_SCRIPT_COLUMNS} FROM omnix_voice_scripts WHERE workspace_id = %s AND id = %s",
            (workspace, script_id),
        ).fetchone()
        if row is None:
            raise ScriptNotFound(script_id)
        lines = [_line_row(line) for line in connection.execute(
            f"SELECT {_LINE_COLUMNS} FROM omnix_voice_script_lines WHERE workspace_id = %s AND script_id = %s ORDER BY position",
            (workspace, script_id),
        ).fetchall()]
        takes = [_take_row(take) for take in connection.execute(
            f"SELECT {_TAKE_COLUMNS} FROM omnix_voice_takes WHERE workspace_id = %s AND script_id = %s ORDER BY created_at DESC",
            (workspace, script_id),
        ).fetchall()]
    by_line: dict[str, list[dict[str, Any]]] = {}
    for take in takes:
        by_line.setdefault(take["line_id"], []).append(take)
    for line in lines:
        line["takes"] = by_line.get(line["id"], [])
    return {**_script_row(row), "lines": lines}


def list_scripts(limit: int = 50) -> list[dict[str, Any]]:
    workspace = _workspace()
    with unit_of_work() as work:
        rows = work.connection.execute(
            f"SELECT {_SCRIPT_COLUMNS} FROM omnix_voice_scripts WHERE workspace_id = %s ORDER BY updated_at DESC LIMIT %s",
            (workspace, max(1, min(int(limit), 200))),
        ).fetchall()
    return [_script_row(row) for row in rows]


def delete_script(script_id: str) -> bool:
    workspace = _workspace()
    with unit_of_work() as work:
        deleted = work.connection.execute(
            "DELETE FROM omnix_voice_scripts WHERE workspace_id = %s AND id = %s RETURNING id", (workspace, script_id),
        ).fetchone()
        work.commit()
    return deleted is not None


def record_take(*, script_id: str, line_id: str, asset_id: str, job_id: str, engine: str, text: str,
                duration: float, select: bool = True) -> dict[str, Any]:
    """Keep a new take for a line and, by default, select it."""
    workspace = _workspace()
    take_id = f"vtake:{uuid.uuid4().hex}"
    with unit_of_work() as work:
        connection = work.connection
        line = connection.execute(
            "SELECT id FROM omnix_voice_script_lines WHERE workspace_id = %s AND id = %s AND script_id = %s FOR UPDATE",
            (workspace, line_id, script_id),
        ).fetchone()
        if line is None:
            raise ScriptNotFound(line_id)
        connection.execute(
            """INSERT INTO omnix_voice_takes
                   (id, workspace_id, script_id, line_id, asset_id, job_id, engine, text_hash, duration_seconds)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (take_id, workspace, script_id, line_id, asset_id, job_id, engine, text_hash(text), duration),
        )
        if select:
            connection.execute(
                "UPDATE omnix_voice_script_lines SET selected_take_id = %s WHERE workspace_id = %s AND id = %s",
                (take_id, workspace, line_id),
            )
        work.commit()
    return {"id": take_id, "line_id": line_id, "asset_id": asset_id}


def select_take(*, script_id: str, line_id: str, take_id: str) -> None:
    workspace = _workspace()
    with unit_of_work() as work:
        updated = work.connection.execute(
            """UPDATE omnix_voice_script_lines SET selected_take_id = %s
                WHERE workspace_id = %s AND id = %s AND script_id = %s
                  AND EXISTS (SELECT 1 FROM omnix_voice_takes
                               WHERE workspace_id = %s AND id = %s AND line_id = %s)
               RETURNING id""",
            (take_id, workspace, line_id, script_id, workspace, take_id, line_id),
        ).fetchone()
        if updated is None:
            raise ScriptNotFound(take_id)
        work.commit()


def pin_take(*, take_id: str, pinned: bool) -> None:
    workspace = _workspace()
    with unit_of_work() as work:
        work.connection.execute(
            "UPDATE omnix_voice_takes SET pinned = %s WHERE workspace_id = %s AND id = %s",
            (bool(pinned), workspace, take_id),
        )
        work.commit()


__all__ = [
    "ScriptNotFound",
    "ScriptRevisionConflict",
    "delete_script",
    "get_script",
    "list_scripts",
    "pin_take",
    "record_take",
    "save_script",
    "select_take",
    "text_hash",
]
