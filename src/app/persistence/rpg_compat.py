from __future__ import annotations

import hashlib
from typing import Any

from .database import PostgresDatabase, default_database
from .errors import RevisionConflict
from .identity_service import bootstrap_local_tenant
from .rpg_repository import canonical_json, state_hash
from .rpg_session_save_policy import session_save_deferred
from .runtime import ensure_postgresql_runtime_ready
from .unit_of_work import unit_of_work


def _database() -> PostgresDatabase:
    database = default_database()
    ensure_postgresql_runtime_ready(database)
    return database


def _context(database: PostgresDatabase):
    return bootstrap_local_tenant(database)


def _campaign_id(session: dict[str, Any]) -> str:
    manifest = session.get("manifest") if isinstance(session.get("manifest"), dict) else {}
    value = str(manifest.get("session_id") or manifest.get("id") or "").strip()
    if not value:
        raise ValueError("RPG session manifest requires session_id")
    return value


def _revision(session: dict[str, Any]) -> int:
    runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    manifest = session.get("manifest") if isinstance(session.get("manifest"), dict) else {}
    return max(0, int(runtime.get("state_revision") or manifest.get("turn_count") or 0))


def save_session_to_postgres(
    session: dict[str, Any],
    *,
    compact: bool = False,
) -> dict[str, Any]:
    del compact
    if session_save_deferred():
        return session
    database = _database()
    context = _context(database)
    campaign_id = _campaign_id(session)
    revision = _revision(session)
    digest = state_hash(session)
    manifest = session.get("manifest") if isinstance(session.get("manifest"), dict) else {}
    engine_version = str(
        manifest.get("engine_version") or session.get("engine_version") or "rpg-engine"
    )
    schema_version = str(session.get("save_version") or "rpg-session-v1")
    seed = str(manifest.get("seed") or session.get("seed") or campaign_id)
    title = str(manifest.get("title") or campaign_id)

    with unit_of_work(database) as work:
        existing = work.rpg.get_campaign(context, campaign_id, for_update=True)
        if existing is None:
            work.connection.execute(
                """
                INSERT INTO omnix_rpg_campaigns (
                    id, workspace_id, owner_user_id, title, revision, state_jsonb,
                    state_hash, engine_version, schema_version, seed, status, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    campaign_id,
                    context.workspace_id,
                    context.user_id,
                    title,
                    revision,
                    canonical_json(session),
                    digest,
                    engine_version,
                    schema_version,
                    seed,
                    "archived" if manifest.get("archived") else "active",
                    canonical_json({"compatibility_save": True}),
                ),
            )
            work.connection.execute(
                """
                INSERT INTO omnix_rpg_participants
                    (campaign_id, user_id, role, permissions)
                VALUES (%s, %s, 'owner', ARRAY['read', 'write', 'admin'])
                ON CONFLICT DO NOTHING
                """,
                (campaign_id, context.user_id),
            )
        else:
            if revision < existing["revision"]:
                raise RevisionConflict(
                    f"RPG session {campaign_id} attempted to save stale revision {revision}; "
                    f"current {existing['revision']}"
                )
            if revision == existing["revision"] and digest == existing["state_hash"]:
                work.rollback()
                return existing["state"]
            if revision == existing["revision"] and digest != existing["state_hash"]:
                revision = existing["revision"] + 1
                runtime = session.get("runtime_state")
                if not isinstance(runtime, dict):
                    runtime = {}
                    session["runtime_state"] = runtime
                runtime["state_revision"] = revision
                digest = state_hash(session)
            cursor = work.connection.execute(
                """
                UPDATE omnix_rpg_campaigns
                   SET title = %s, revision = %s, state_jsonb = %s::jsonb,
                       state_hash = %s, engine_version = %s, schema_version = %s,
                       seed = %s, status = %s, updated_at = CURRENT_TIMESTAMP,
                       metadata = metadata || %s::jsonb
                 WHERE id = %s AND workspace_id = %s AND revision = %s
                """,
                (
                    title,
                    revision,
                    canonical_json(session),
                    digest,
                    engine_version,
                    schema_version,
                    seed,
                    "archived" if manifest.get("archived") else "active",
                    canonical_json({"compatibility_save": True}),
                    campaign_id,
                    context.workspace_id,
                    existing["revision"],
                ),
            )
            if cursor.rowcount != 1:
                raise RevisionConflict(f"RPG session changed while saving: {campaign_id}")
        work.commit()
    return session


def load_session_from_postgres(session_id: str) -> dict[str, Any] | None:
    database = _database()
    context = _context(database)
    with unit_of_work(database) as work:
        campaign = work.rpg.get_campaign(context, session_id)
        work.rollback()
    return dict(campaign["state"]) if campaign is not None else None


def list_sessions_from_postgres() -> list[dict[str, Any]]:
    database = _database()
    context = _context(database)
    with unit_of_work(database) as work:
        campaigns = work.rpg.list_campaigns(context, limit=500, status="active")
        archived = work.rpg.list_campaigns(context, limit=500, status="archived")
        work.rollback()
    return [dict(record["state"]) for record in campaigns + archived]


def list_session_summaries_from_postgres(
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Project the authoritative campaign list into the bounded UI summary contract."""

    from app.rpg.session.list_summaries import session_list_summary

    sessions = list_sessions_from_postgres()
    if limit is not None:
        sessions = sessions[: max(0, int(limit))]
    return [session_list_summary(session) for session in sessions]


def archive_session_in_postgres(session_id: str) -> dict[str, Any]:
    database = _database()
    context = _context(database)
    with database.transaction() as connection:
        row = connection.execute(
            """
            UPDATE omnix_rpg_campaigns
               SET status = 'archived', revision = revision + 1,
                   state_jsonb = jsonb_set(
                       state_jsonb,
                       '{manifest,archived}',
                       'true'::jsonb,
                       TRUE
                   ),
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s
            RETURNING state_jsonb
            """,
            (session_id, context.workspace_id),
        ).fetchone()
    return {"ok": row is not None, "session": dict(row[0]) if row is not None else None}


def append_interaction_event_postgres(
    session_id: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    database = _database()
    context = _context(database)
    interaction_id = str(event.get("interaction_id") or "").strip()
    if not interaction_id:
        canonical = canonical_json(event)
        interaction_id = f"interaction:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
    sequence = int(event.get("sequence") or 0)
    revision = int(event.get("state_revision") or 0)
    with database.transaction() as connection:
        campaign = connection.execute(
            "SELECT id FROM omnix_rpg_campaigns WHERE id = %s AND workspace_id = %s",
            (session_id, context.workspace_id),
        ).fetchone()
        if campaign is None:
            raise KeyError(session_id)
        turn = connection.execute(
            "SELECT id FROM omnix_rpg_turns WHERE campaign_id = %s AND interaction_id = %s",
            (session_id, interaction_id),
        ).fetchone()
        if turn is None:
            turn_id = f"turn:compat:{interaction_id}"
            submission_id = str(event.get("submission_id") or turn_id)
            response = {
                "ok": True,
                "interaction_id": interaction_id,
                "compatibility_record": True,
            }
            campaign_row = connection.execute(
                "SELECT revision, state_hash, engine_version, schema_version "
                "FROM omnix_rpg_campaigns WHERE id = %s FOR UPDATE",
                (session_id,),
            ).fetchone()
            resulting_revision = max(revision, int(campaign_row[0]))
            sequence = max(sequence, resulting_revision, 1)
            connection.execute(
                """
                INSERT INTO omnix_rpg_turns (
                    id, workspace_id, campaign_id, sequence, submission_id,
                    expected_revision, resulting_revision, command_jsonb,
                    canonical_effects_jsonb, state_hash_before, state_hash_after,
                    engine_version, schema_version, interaction_id, compact_response
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, '{}'::jsonb, '{}'::jsonb,
                          %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (campaign_id, interaction_id) DO NOTHING
                """,
                (
                    turn_id,
                    context.workspace_id,
                    session_id,
                    sequence,
                    submission_id,
                    max(0, resulting_revision - 1),
                    max(1, resulting_revision),
                    campaign_row[1],
                    campaign_row[1],
                    campaign_row[2],
                    campaign_row[3],
                    interaction_id,
                    canonical_json(response),
                ),
            )
            turn = (turn_id,)
        connection.execute(
            """
            INSERT INTO omnix_rpg_interactions (
                interaction_id, workspace_id, campaign_id, turn_id, sequence,
                state_revision, event_jsonb
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (interaction_id) DO UPDATE SET
                event_jsonb = EXCLUDED.event_jsonb,
                state_revision = EXCLUDED.state_revision
            """,
            (
                interaction_id,
                context.workspace_id,
                session_id,
                str(turn[0]),
                max(1, sequence),
                max(0, revision),
                canonical_json(event),
            ),
        )
    canonical = canonical_json(event)
    return {
        "format_version": "rpg_interaction_event_log_v1",
        "checksum": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "event": event,
    }


def load_interaction_events_postgres(
    session_id: str,
    *,
    after_sequence: int = 0,
    limit: int = 1_000,
) -> list[dict[str, Any]]:
    database = _database()
    context = _context(database)
    with database.connection() as connection:
        rows = connection.execute(
            """
            SELECT event_jsonb FROM omnix_rpg_interactions
             WHERE workspace_id = %s AND campaign_id = %s AND sequence > %s
             ORDER BY sequence ASC LIMIT %s
            """,
            (
                context.workspace_id,
                session_id,
                int(after_sequence),
                max(1, min(int(limit), 5000)),
            ),
        ).fetchall()
    return [dict(row[0]) for row in rows]


def compact_interaction_events_postgres(
    session_id: str,
    *,
    through_sequence: int,
) -> int:
    database = _database()
    context = _context(database)
    with database.connection() as connection:
        remaining = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM omnix_rpg_interactions
                 WHERE workspace_id = %s AND campaign_id = %s AND sequence > %s
                """,
                (context.workspace_id, session_id, int(through_sequence)),
            ).fetchone()[0]
        )
    return remaining


def interaction_log_status_postgres(session_id: str) -> dict[str, Any]:
    database = _database()
    context = _context(database)
    with database.connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(octet_length(event_jsonb::text)), 0)
              FROM omnix_rpg_interactions
             WHERE workspace_id = %s AND campaign_id = %s
            """,
            (context.workspace_id, session_id),
        ).fetchone()
    return {
        "format_version": "rpg_interaction_event_log_v1",
        "path": "postgresql://omnix_rpg_interactions",
        "exists": int(row[0]) > 0,
        "size_bytes": int(row[1]),
        "event_count": int(row[0]),
        "compaction_required": False,
    }
