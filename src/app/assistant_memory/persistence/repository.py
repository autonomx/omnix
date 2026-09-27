from __future__ import annotations

import json
from typing import Any

from app.persistence.errors import EntityNotFound, RevisionConflict
from app.persistence.tenant import TenantContext


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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


