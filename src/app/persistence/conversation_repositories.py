from __future__ import annotations

import json
from typing import Any

from .errors import EntityNotFound, RevisionConflict
from .tenant import TenantContext


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _character(row: Any) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "workspace_id": str(row[1]),
        "owner_user_id": str(row[2]) if row[2] is not None else None,
        "visibility": str(row[3]),
        "active_version": int(row[4]),
        "status": str(row[5]),
        "enabled": bool(row[6]),
        "revision": int(row[7]),
        "profile": dict(row[8]),
        "created_at": row[9].isoformat(),
        "updated_at": row[10].isoformat(),
    }


_CHARACTER_COLUMNS = """
id, workspace_id, owner_user_id, visibility, active_version, status,
enabled, revision, profile, created_at, updated_at
"""


class PostgresCharacterRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create(
        self,
        context: TenantContext,
        *,
        character_id: str,
        profile: dict[str, Any],
        visibility: str = "private",
        enabled: bool = True,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            f"""
            INSERT INTO omnix_characters
                (id, workspace_id, owner_user_id, visibility, enabled, profile)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING {_CHARACTER_COLUMNS}
            """,
            (
                character_id,
                context.workspace_id,
                context.user_id,
                visibility,
                enabled,
                _json(profile),
            ),
        ).fetchone()
        self.connection.execute(
            """
            INSERT INTO omnix_character_versions
                (character_id, version, profile, created_by)
            VALUES (%s, 1, %s::jsonb, %s)
            """,
            (character_id, _json(profile), context.user_id),
        )
        return _character(row)

    def get_character(
        self,
        context: TenantContext,
        character_id: str,
        *,
        include_archived: bool = False,
    ) -> dict[str, Any] | None:
        status_clause = "" if include_archived else " AND status = 'active'"
        row = self.connection.execute(
            f"SELECT {_CHARACTER_COLUMNS} FROM omnix_characters "
            f"WHERE id = %s AND workspace_id = %s{status_clause}",
            (character_id, context.workspace_id),
        ).fetchone()
        return _character(row) if row is not None else None

    def list_characters(
        self,
        context: TenantContext,
        *,
        include_archived: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        status_clause = "" if include_archived else " AND status = 'active'"
        rows = self.connection.execute(
            f"SELECT {_CHARACTER_COLUMNS} FROM omnix_characters "
            f"WHERE workspace_id = %s{status_clause} "
            "ORDER BY lower(profile->>'display_name'), id LIMIT %s",
            (context.workspace_id, max(1, min(int(limit), 500))),
        ).fetchall()
        return [_character(row) for row in rows]

    def update(
        self,
        context: TenantContext,
        *,
        character_id: str,
        profile: dict[str, Any],
        expected_version: int,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            f"""
            UPDATE omnix_characters
               SET profile = %s::jsonb,
                   active_version = active_version + 1,
                   revision = revision + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s AND status = 'active'
               AND active_version = %s
            RETURNING {_CHARACTER_COLUMNS}
            """,
            (_json(profile), character_id, context.workspace_id, expected_version),
        ).fetchone()
        if row is None:
            current = self.connection.execute(
                "SELECT active_version FROM omnix_characters "
                "WHERE id = %s AND workspace_id = %s",
                (character_id, context.workspace_id),
            ).fetchone()
            if current is None:
                raise EntityNotFound(character_id)
            raise RevisionConflict(
                f"character {character_id} expected version {expected_version}; current {int(current[0])}"
            )
        result = _character(row)
        self.connection.execute(
            """
            INSERT INTO omnix_character_versions
                (character_id, version, profile, created_by)
            VALUES (%s, %s, %s::jsonb, %s)
            """,
            (character_id, result["active_version"], _json(profile), context.user_id),
        )
        return result

    def archive(
        self,
        context: TenantContext,
        *,
        character_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            f"""
            UPDATE omnix_characters
               SET status = 'archived', enabled = FALSE,
                   revision = revision + 1, updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s AND revision = %s
            RETURNING {_CHARACTER_COLUMNS}
            """,
            (character_id, context.workspace_id, expected_revision),
        ).fetchone()
        if row is None:
            raise RevisionConflict(
                f"character {character_id} expected revision {expected_revision}"
            )
        return _character(row)

    def versions(self, context: TenantContext, character_id: str) -> list[dict[str, Any]]:
        exists = self.get_character(context, character_id, include_archived=True)
        if exists is None:
            raise EntityNotFound(character_id)
        rows = self.connection.execute(
            """
            SELECT version, profile, created_by, created_at
              FROM omnix_character_versions
             WHERE character_id = %s ORDER BY version DESC
            """,
            (character_id,),
        ).fetchall()
        return [
            {
                "character_id": character_id,
                "version": int(row[0]),
                "profile": dict(row[1]),
                "created_by": str(row[2]) if row[2] is not None else None,
                "created_at": row[3].isoformat(),
            }
            for row in rows
        ]


def _memory(row: Any) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "workspace_id": str(row[1]),
        "owner_type": str(row[2]),
        "owner_id": str(row[3]),
        "category": str(row[4]),
        "content": str(row[5]),
        "normalized_content": str(row[6]),
        "confidence": float(row[7]),
        "pinned": bool(row[8]),
        "trust_level": str(row[9]),
        "sensitivity": str(row[10]),
        "provenance_type": str(row[11]) if row[11] is not None else None,
        "provenance_id": str(row[12]) if row[12] is not None else None,
        "source": str(row[13]),
        "status": str(row[14]),
        "revision": int(row[15]),
        "created_at": row[16].isoformat(),
        "updated_at": row[17].isoformat(),
        "expires_at": row[18].isoformat() if row[18] is not None else None,
    }


_MEMORY_COLUMNS = """
id, workspace_id, owner_type, owner_id, category, content,
normalized_content, confidence, pinned, trust_level, sensitivity,
provenance_type, provenance_id, source, status, revision, created_at,
updated_at, expires_at
"""


class PostgresMemoryRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create(self, context: TenantContext, payload: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            f"""
            INSERT INTO omnix_memory_records (
                id, workspace_id, owner_type, owner_id, category, content,
                normalized_content, confidence, pinned, trust_level, sensitivity,
                provenance_type, provenance_id, source, status, expires_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            ) RETURNING {_MEMORY_COLUMNS}
            """,
            (
                payload["id"],
                context.workspace_id,
                payload["owner_type"],
                payload["owner_id"],
                payload["category"],
                payload["content"],
                payload.get("normalized_content") or str(payload["content"]).strip().lower(),
                float(payload.get("confidence", 1.0)),
                bool(payload.get("pinned", False)),
                payload.get("trust_level", "normal"),
                payload.get("sensitivity", "normal"),
                payload.get("provenance_type"),
                payload.get("provenance_id"),
                payload.get("source", "user"),
                payload.get("status", "active"),
                payload.get("expires_at"),
            ),
        ).fetchone()
        result = _memory(row)
        self._event(context, "record", result["id"], "memory.created", {"revision": 1})
        return result

    def get_memory(self, context: TenantContext, memory_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {_MEMORY_COLUMNS} FROM omnix_memory_records "
            "WHERE id = %s AND workspace_id = %s",
            (memory_id, context.workspace_id),
        ).fetchone()
        return _memory(row) if row is not None else None

    def list_records(
        self,
        context: TenantContext,
        *,
        owner_type: str,
        owner_id: str,
        status: str = "active",
        limit: int = 100,
        before_updated_at: str | None = None,
        before_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = [
            "workspace_id = %s",
            "owner_type = %s",
            "owner_id = %s",
            "status = %s",
        ]
        params: list[Any] = [context.workspace_id, owner_type, owner_id, status]
        if before_updated_at is not None and before_id is not None:
            clauses.append("(updated_at, id) < (%s::timestamptz, %s)")
            params.extend([before_updated_at, before_id])
        params.append(max(1, min(int(limit), 500)))
        rows = self.connection.execute(
            f"SELECT {_MEMORY_COLUMNS} FROM omnix_memory_records WHERE "
            + " AND ".join(clauses)
            + " ORDER BY pinned DESC, updated_at DESC, id DESC LIMIT %s",
            tuple(params),
        ).fetchall()
        return [_memory(row) for row in rows]

    def update(
        self,
        context: TenantContext,
        *,
        memory_id: str,
        expected_revision: int,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        current = self.get_memory(context, memory_id)
        if current is None:
            raise EntityNotFound(memory_id)
        merged = dict(current)
        for key in (
            "category",
            "content",
            "normalized_content",
            "confidence",
            "pinned",
            "trust_level",
            "sensitivity",
            "provenance_type",
            "provenance_id",
            "source",
            "status",
            "expires_at",
        ):
            if key in changes:
                merged[key] = changes[key]
        row = self.connection.execute(
            f"""
            UPDATE omnix_memory_records SET
                category = %s, content = %s, normalized_content = %s,
                confidence = %s, pinned = %s, trust_level = %s,
                sensitivity = %s, provenance_type = %s, provenance_id = %s,
                source = %s, status = %s, expires_at = %s,
                revision = revision + 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND workspace_id = %s AND revision = %s
            RETURNING {_MEMORY_COLUMNS}
            """,
            (
                merged["category"],
                merged["content"],
                merged["normalized_content"],
                merged["confidence"],
                merged["pinned"],
                merged["trust_level"],
                merged["sensitivity"],
                merged["provenance_type"],
                merged["provenance_id"],
                merged["source"],
                merged["status"],
                merged["expires_at"],
                memory_id,
                context.workspace_id,
                expected_revision,
            ),
        ).fetchone()
        if row is None:
            raise RevisionConflict(
                f"memory {memory_id} expected revision {expected_revision}; current {current['revision']}"
            )
        result = _memory(row)
        self._event(
            context, "record", memory_id, "memory.updated", {"revision": result["revision"]}
        )
        return result

    def create_candidate(
        self, context: TenantContext, payload: dict[str, Any]
    ) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO omnix_memory_candidates (
                id, workspace_id, source_session_id, source_message_id,
                candidate_fingerprint, proposed_owner_type, proposed_owner_id,
                proposed_category, proposed_content, confidence, source,
                trust_level, sensitivity, extraction_metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (workspace_id, source_message_id, candidate_fingerprint)
            DO UPDATE SET id = omnix_memory_candidates.id
            RETURNING id, source_session_id, source_message_id, candidate_fingerprint,
                      proposed_owner_type, proposed_owner_id, proposed_category,
                      proposed_content, confidence, source, trust_level, sensitivity,
                      extraction_metadata, status, created_at, resolved_at
            """,
            (
                payload["id"],
                context.workspace_id,
                payload.get("source_session_id"),
                payload["source_message_id"],
                payload["candidate_fingerprint"],
                payload["proposed_owner_type"],
                payload["proposed_owner_id"],
                payload["proposed_category"],
                payload["proposed_content"],
                float(payload.get("confidence", 1.0)),
                payload.get("source", "assistant"),
                payload.get("trust_level", "normal"),
                payload.get("sensitivity", "normal"),
                _json(payload.get("extraction_metadata") or {}),
            ),
        ).fetchone()
        return {
            "id": str(row[0]),
            "source_session_id": str(row[1]) if row[1] is not None else None,
            "source_message_id": str(row[2]),
            "candidate_fingerprint": str(row[3]),
            "proposed_owner_type": str(row[4]),
            "proposed_owner_id": str(row[5]),
            "proposed_category": str(row[6]),
            "proposed_content": str(row[7]),
            "confidence": float(row[8]),
            "source": str(row[9]),
            "trust_level": str(row[10]),
            "sensitivity": str(row[11]),
            "extraction_metadata": dict(row[12]),
            "status": str(row[13]),
            "created_at": row[14].isoformat(),
            "resolved_at": row[15].isoformat() if row[15] is not None else None,
        }

    def create_snapshot(
        self,
        context: TenantContext,
        *,
        snapshot_id: str,
        owner_type: str,
        owner_id: str,
        record_ids: list[str],
    ) -> dict[str, Any]:
        revision = int(
            self.connection.execute(
                """
                SELECT COALESCE(MAX(revision), 0) + 1
                  FROM omnix_memory_snapshots
                 WHERE workspace_id = %s AND owner_type = %s AND owner_id = %s
                """,
                (context.workspace_id, owner_type, owner_id),
            ).fetchone()[0]
        )
        self.connection.execute(
            """
            INSERT INTO omnix_memory_snapshots
                (id, workspace_id, owner_type, owner_id, revision)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (snapshot_id, context.workspace_id, owner_type, owner_id, revision),
        )
        items: list[dict[str, Any]] = []
        for position, record_id in enumerate(record_ids):
            record = self.get_memory(context, record_id)
            if record is None or record["owner_type"] != owner_type or record["owner_id"] != owner_id:
                raise EntityNotFound(record_id)
            self.connection.execute(
                """
                INSERT INTO omnix_memory_snapshot_items
                    (snapshot_id, memory_record_id, position, record_revision)
                VALUES (%s, %s, %s, %s)
                """,
                (snapshot_id, record_id, position, record["revision"]),
            )
            items.append(
                {
                    "memory_record_id": record_id,
                    "position": position,
                    "record_revision": record["revision"],
                }
            )
        self._event(
            context, "snapshot", snapshot_id, "memory.snapshot_created", {"revision": revision}
        )
        return {
            "id": snapshot_id,
            "workspace_id": context.workspace_id,
            "owner_type": owner_type,
            "owner_id": owner_id,
            "revision": revision,
            "items": items,
        }

    def _event(
        self,
        context: TenantContext,
        entity_type: str,
        entity_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> int:
        row = self.connection.execute(
            """
            INSERT INTO omnix_memory_events
                (workspace_id, entity_type, entity_id, event_type, payload)
            VALUES (%s, %s, %s, %s, %s::jsonb) RETURNING id
            """,
            (context.workspace_id, entity_type, entity_id, event_type, _json(payload)),
        ).fetchone()
        return int(row[0])


def _session(row: Any) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "workspace_id": str(row[1]),
        "owner_user_id": str(row[2]) if row[2] is not None else None,
        "title": str(row[3]),
        "provider_id": str(row[4]) if row[4] is not None else None,
        "model_id": str(row[5]) if row[5] is not None else None,
        "project_id": str(row[6]) if row[6] is not None else None,
        "profile_id": str(row[7]) if row[7] is not None else None,
        "interaction_mode": str(row[8]),
        "character_id": str(row[9]) if row[9] is not None else None,
        "character_version": int(row[10]) if row[10] is not None else None,
        "memory_enabled": bool(row[11]),
        "memory_snapshot_id": str(row[12]) if row[12] is not None else None,
        "settings": dict(row[13]),
        "transcript_policy": str(row[14]),
        "active_segment_id": str(row[15]) if row[15] is not None else None,
        "status": str(row[16]),
        "revision": int(row[17]),
        "message_count": int(row[18]),
        "created_at": row[19].isoformat(),
        "updated_at": row[20].isoformat(),
    }


_SESSION_COLUMNS = """
id, workspace_id, owner_user_id, title, provider_id, model_id, project_id,
profile_id, interaction_mode, character_id, character_version, memory_enabled,
memory_snapshot_id, settings, transcript_policy, active_segment_id, status,
revision, message_count, created_at, updated_at
"""


class PostgresChatRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create_session(
        self, context: TenantContext, payload: dict[str, Any]
    ) -> dict[str, Any]:
        row = self.connection.execute(
            f"""
            INSERT INTO omnix_chat_sessions (
                id, workspace_id, owner_user_id, title, provider_id, model_id,
                project_id, profile_id, interaction_mode, character_id,
                character_version, memory_enabled, memory_snapshot_id, settings,
                transcript_policy, active_segment_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s::jsonb, %s, %s
            ) RETURNING {_SESSION_COLUMNS}
            """,
            (
                payload["id"],
                context.workspace_id,
                payload.get("owner_user_id") or context.user_id,
                payload.get("title") or "New chat",
                payload.get("provider_id"),
                payload.get("model_id"),
                payload.get("project_id"),
                payload.get("profile_id"),
                payload.get("interaction_mode", "system"),
                payload.get("character_id"),
                payload.get("character_version"),
                bool(payload.get("memory_enabled", False)),
                payload.get("memory_snapshot_id"),
                _json(payload.get("settings") or {}),
                payload.get("transcript_policy", "persistent"),
                payload.get("active_segment_id"),
            ),
        ).fetchone()
        return _session(row)

    def get_session(self, context: TenantContext, session_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {_SESSION_COLUMNS} FROM omnix_chat_sessions "
            "WHERE id = %s AND workspace_id = %s",
            (session_id, context.workspace_id),
        ).fetchone()
        return _session(row) if row is not None else None

    def list_sessions(
        self,
        context: TenantContext,
        *,
        limit: int = 50,
        before_updated_at: str | None = None,
        before_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["workspace_id = %s", "status = 'active'"]
        params: list[Any] = [context.workspace_id]
        if before_updated_at is not None and before_id is not None:
            clauses.append("(updated_at, id) < (%s::timestamptz, %s)")
            params.extend([before_updated_at, before_id])
        params.append(max(1, min(int(limit), 200)))
        rows = self.connection.execute(
            f"SELECT {_SESSION_COLUMNS} FROM omnix_chat_sessions WHERE "
            + " AND ".join(clauses)
            + " ORDER BY updated_at DESC, id DESC LIMIT %s",
            tuple(params),
        ).fetchall()
        return [_session(row) for row in rows]

    def update_session(
        self,
        context: TenantContext,
        *,
        session_id: str,
        expected_revision: int,
        title: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.get_session(context, session_id)
        if current is None:
            raise EntityNotFound(session_id)
        row = self.connection.execute(
            f"""
            UPDATE omnix_chat_sessions
               SET title = %s, settings = %s::jsonb,
                   revision = revision + 1, updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s AND revision = %s
            RETURNING {_SESSION_COLUMNS}
            """,
            (
                title if title is not None else current["title"],
                _json(settings if settings is not None else current["settings"]),
                session_id,
                context.workspace_id,
                expected_revision,
            ),
        ).fetchone()
        if row is None:
            raise RevisionConflict(
                f"chat session {session_id} expected revision {expected_revision}; current {current['revision']}"
            )
        return _session(row)

    def append_message(
        self,
        context: TenantContext,
        session_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        session = self.connection.execute(
            """
            SELECT message_count FROM omnix_chat_sessions
             WHERE id = %s AND workspace_id = %s AND status = 'active'
             FOR UPDATE
            """,
            (session_id, context.workspace_id),
        ).fetchone()
        if session is None:
            raise EntityNotFound(session_id)
        position = int(session[0])
        row = self.connection.execute(
            """
            INSERT INTO omnix_chat_messages
                (id, workspace_id, session_id, position, role, content, metadata, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            RETURNING id, session_id, position, role, content, metadata, created_at
            """,
            (
                payload["id"],
                context.workspace_id,
                session_id,
                position,
                payload["role"],
                payload["content"],
                _json(payload.get("metadata") or {}),
                payload.get("created_at"),
            ),
        ).fetchone()
        self.connection.execute(
            """
            UPDATE omnix_chat_sessions
               SET message_count = message_count + 1,
                   revision = revision + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s
            """,
            (session_id, context.workspace_id),
        )
        return {
            "id": str(row[0]),
            "session_id": str(row[1]),
            "position": int(row[2]),
            "role": str(row[3]),
            "content": str(row[4]),
            "metadata": dict(row[5]),
            "created_at": row[6].isoformat(),
        }

    def list_messages(
        self,
        context: TenantContext,
        session_id: str,
        *,
        limit: int = 100,
        after_position: int = -1,
    ) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id, session_id, position, role, content, metadata, created_at
              FROM omnix_chat_messages
             WHERE workspace_id = %s AND session_id = %s AND position > %s
             ORDER BY position ASC, id ASC LIMIT %s
            """,
            (
                context.workspace_id,
                session_id,
                int(after_position),
                max(1, min(int(limit), 500)),
            ),
        ).fetchall()
        return [
            {
                "id": str(row[0]),
                "session_id": str(row[1]),
                "position": int(row[2]),
                "role": str(row[3]),
                "content": str(row[4]),
                "metadata": dict(row[5]),
                "created_at": row[6].isoformat(),
            }
            for row in rows
        ]
