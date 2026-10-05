"""What the kernel reads about assistant memory without loading it (ADR-0016): kernel imports only."""
from __future__ import annotations

import json
from typing import Any

from app.persistence.declarations import LegacyImport


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _restore_memory_lifecycle(work: Any, context: Any, _stable_id: str, item: dict[str, Any]) -> None:
    """A legacy memory record's candidates, snapshots and events (PA-2.2)."""
    for candidate in list(item.get("candidates") or []):
        work.connection.execute(
            """
            INSERT INTO omnix_memory_candidates (
                id, workspace_id, source_session_id, source_message_id,
                candidate_fingerprint, proposed_owner_type, proposed_owner_id,
                proposed_category, proposed_content, confidence, source,
                trust_level, sensitivity, extraction_metadata, status,
                created_at, resolved_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s, COALESCE(%s::timestamptz, CURRENT_TIMESTAMP),
                %s::timestamptz
            ) ON CONFLICT (id) DO NOTHING
            """,
            (
                candidate["id"],
                context.workspace_id,
                candidate.get("source_session_id"),
                candidate.get("source_message_id") or candidate["id"],
                candidate.get("candidate_fingerprint") or candidate["id"],
                candidate.get("proposed_owner_type", "workspace"),
                candidate.get("proposed_owner_id", context.workspace_id),
                candidate.get("proposed_category", "fact"),
                candidate.get("proposed_content", ""),
                float(candidate.get("confidence", 0.5)),
                candidate.get("source", "imported"),
                candidate.get("trust_level", "unverified_import"),
                candidate.get("sensitivity", "normal"),
                _json(candidate.get("extraction_metadata") or {}),
                candidate.get("status", "pending"),
                candidate.get("created_at"),
                candidate.get("resolved_at"),
            ),
        )
    for snapshot in list(item.get("snapshots") or []):
        work.connection.execute(
            """
            INSERT INTO omnix_memory_snapshots (
                id, workspace_id, owner_type, owner_id, revision, status,
                session_id, token_estimate, created_at, refreshed_at
            ) VALUES (
                %s, %s, %s, %s, %s, 'active', %s, %s,
                COALESCE(%s::timestamptz, CURRENT_TIMESTAMP), %s::timestamptz
            ) ON CONFLICT (id) DO NOTHING
            """,
            (
                snapshot["id"],
                context.workspace_id,
                snapshot.get("owner_type", "system"),
                snapshot.get("owner_id", "system-assistant"),
                int(snapshot.get("revision", 1)),
                snapshot.get("session_id"),
                int(snapshot.get("token_estimate", 0)),
                snapshot.get("created_at"),
                snapshot.get("refreshed_at"),
            ),
        )
        for position, entry in enumerate(list(snapshot.get("items") or [])):
            work.connection.execute(
                """
                INSERT INTO omnix_memory_snapshot_items (
                    snapshot_id, memory_record_id, position, record_revision,
                    frozen_content, revoked_at
                ) VALUES (%s, %s, %s, %s, %s, %s::timestamptz)
                ON CONFLICT (snapshot_id, memory_record_id) DO NOTHING
                """,
                (
                    snapshot["id"],
                    entry["memory_record_id"],
                    int(entry.get("position", position)),
                    int(entry.get("record_revision", 1)),
                    entry.get("frozen_content"),
                    entry.get("revoked_at"),
                ),
            )
    for event in list(item.get("events") or []):
        work.connection.execute(
            """
            INSERT INTO omnix_memory_events (
                workspace_id, entity_type, entity_id, event_type, payload, created_at
            ) VALUES (%s, %s, %s, %s, %s::jsonb,
                      COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                context.workspace_id,
                event.get("entity_type", "memory"),
                event.get("entity_id") or event.get("id") or "legacy",
                event.get("event_type", "legacy.event"),
                _json(event.get("payload") or {}),
                event.get("created_at"),
            ),
        )


LEGACY_IMPORTS = (LegacyImport("assistant-memory.lifecycle", _restore_memory_lifecycle),)
