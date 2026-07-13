"""Complete legacy importer extensions for lifecycle and replay records."""

from __future__ import annotations

import json
from typing import Any

from .cutover import PostgresLegacyImporter
from .rpg_repository import canonical_json, state_hash
from .tenant import TenantContext


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class CompletePostgresLegacyImporter(PostgresLegacyImporter):
    """Restore lifecycle records nested in their owning legacy aggregates."""

    def _dispatch(
        self,
        work: Any,
        context: TenantContext,
        entity_type: str,
        stable_id: str,
        item: dict[str, Any],
    ) -> tuple[str, str, str | None]:
        if entity_type == "characters" and item.get("_migration_envelope"):
            self._segments(work, context, list(item.get("conversation_segments") or []))
            return "omnix_conversation_segments", stable_id, None
        if entity_type == "memory_records" and item.get("_migration_envelope"):
            self._memory_lifecycle(work, context, item)
            return "omnix_memory_events", stable_id, None

        target = super()._dispatch(work, context, entity_type, stable_id, item)
        if entity_type == "characters":
            self._segments(work, context, list(item.get("conversation_segments") or []))
        elif entity_type == "jobs":
            self._job_history(work, context, stable_id, item)
        elif entity_type == "rpg_campaigns":
            self._rpg_history(work, context, stable_id, item)
        return target

    @staticmethod
    def _segments(work: Any, context: TenantContext, segments: list[dict[str, Any]]) -> None:
        for item in segments:
            segment_id = str(item.get("id") or "").strip()
            session_id = str(item.get("session_id") or "").strip()
            if not segment_id or not session_id:
                continue
            work.connection.execute(
                """
                INSERT INTO omnix_conversation_segments (
                    id, workspace_id, session_id, interaction_mode, character_id,
                    character_version, transcript_policy, read_memory, write_memory,
                    shared_memory_access, carryover_summary, started_at, ended_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP), %s::timestamptz
                ) ON CONFLICT (id) DO NOTHING
                """,
                (
                    segment_id,
                    context.workspace_id,
                    session_id,
                    item.get("interaction_mode", "system"),
                    item.get("character_id"),
                    item.get("character_version"),
                    item.get("transcript_policy", "persistent"),
                    bool(item.get("read_memory", False)),
                    bool(item.get("write_memory", False)),
                    item.get("shared_memory_access", "none"),
                    item.get("carryover_summary"),
                    item.get("started_at"),
                    item.get("ended_at"),
                ),
            )

    @staticmethod
    def _memory_lifecycle(work: Any, context: TenantContext, item: dict[str, Any]) -> None:
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

    @staticmethod
    def _job_history(
        work: Any,
        context: TenantContext,
        job_id: str,
        item: dict[str, Any],
    ) -> None:
        for event in list(item.get("events") or []):
            work.connection.execute(
                """
                INSERT INTO omnix_job_events (
                    workspace_id, job_id, event_type, payload, created_at
                ) VALUES (%s, %s, %s, %s::jsonb,
                          COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
                """,
                (
                    context.workspace_id,
                    job_id,
                    event.get("event_type", "legacy.event"),
                    _json(event.get("payload") or {}),
                    event.get("created_at"),
                ),
            )
        attempt_count = int(item.get("attempt_count", 0))
        lease = dict((item.get("metadata") or {}).get("lease") or {})
        for attempt in range(1, attempt_count + 1):
            token = str(lease.get("token") or lease.get("lease_token") or f"legacy:{job_id}:{attempt}")
            worker = str(lease.get("worker_id") or lease.get("owner_id") or "worker:legacy")
            status = "completed" if item.get("status") == "completed" else str(item.get("status") or "legacy")
            work.connection.execute(
                """
                INSERT INTO omnix_job_attempts (
                    job_id, attempt, worker_id, lease_token, status,
                    started_at, completed_at, error
                ) VALUES (%s, %s, %s, %s, %s,
                          COALESCE(%s::timestamptz, CURRENT_TIMESTAMP),
                          %s::timestamptz, %s::jsonb)
                ON CONFLICT (job_id, attempt) DO NOTHING
                """,
                (
                    job_id,
                    attempt,
                    worker,
                    token,
                    status,
                    lease.get("claimed_at"),
                    item.get("completed_at"),
                    _json(item.get("error")) if item.get("error") is not None else None,
                ),
            )

    @staticmethod
    def _rpg_history(
        work: Any,
        context: TenantContext,
        campaign_id: str,
        item: dict[str, Any],
    ) -> None:
        digest = str(item.get("state_hash") or state_hash(dict(item.get("state") or {})))
        engine_version = str(item.get("engine_version") or "legacy")
        schema_version = str(item.get("schema_version") or "legacy")
        for index, event in enumerate(list(item.get("interactions") or []), start=1):
            sequence = max(1, int(event.get("sequence") or index))
            revision = max(1, int(event.get("state_revision") or sequence))
            interaction_id = str(event.get("interaction_id") or f"interaction:{campaign_id}:{sequence}")
            turn_id = str(event.get("turn_id") or f"turn:legacy:{campaign_id}:{sequence}")
            submission_id = str(event.get("submission_id") or f"submission:legacy:{campaign_id}:{sequence}")
            command = {"player_input": str(event.get("player_input") or "")}
            response = {
                "ok": True,
                "interaction_id": interaction_id,
                "submission_id": submission_id,
                "visible_response": event.get("visible_response") or {},
                "legacy_import": True,
            }
            work.connection.execute(
                """
                INSERT INTO omnix_rpg_turns (
                    id, workspace_id, campaign_id, sequence, submission_id,
                    expected_revision, resulting_revision, command_jsonb,
                    canonical_effects_jsonb, state_hash_before, state_hash_after,
                    engine_version, schema_version, interaction_id, compact_response,
                    created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s::jsonb, '{}'::jsonb,
                    %s, %s, %s, %s, %s, %s::jsonb,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP)
                ) ON CONFLICT (campaign_id, interaction_id) DO NOTHING
                """,
                (
                    turn_id,
                    context.workspace_id,
                    campaign_id,
                    sequence,
                    submission_id,
                    max(0, revision - 1),
                    revision,
                    canonical_json(command),
                    digest,
                    digest,
                    engine_version,
                    schema_version,
                    interaction_id,
                    canonical_json(response),
                    event.get("created_at"),
                ),
            )
            turn = work.connection.execute(
                "SELECT id FROM omnix_rpg_turns WHERE campaign_id = %s AND interaction_id = %s",
                (campaign_id, interaction_id),
            ).fetchone()
            if turn is not None:
                work.connection.execute(
                    """
                    INSERT INTO omnix_rpg_interactions (
                        interaction_id, workspace_id, campaign_id, turn_id,
                        sequence, state_revision, event_jsonb, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb,
                              COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
                    ON CONFLICT (interaction_id) DO NOTHING
                    """,
                    (
                        interaction_id,
                        context.workspace_id,
                        campaign_id,
                        str(turn[0]),
                        sequence,
                        revision,
                        canonical_json(event),
                        event.get("created_at"),
                    ),
                )
        for submission in list(item.get("foreground_submissions") or []):
            job_id = submission.get("job_id")
            if job_id:
                exists = work.connection.execute(
                    "SELECT 1 FROM omnix_jobs WHERE id = %s",
                    (job_id,),
                ).fetchone()
                if exists is None:
                    job_id = None
            response = submission.get("response")
            interaction_id = None
            if isinstance(response, dict):
                interaction_id = response.get("interaction_id")
            work.connection.execute(
                """
                INSERT INTO omnix_rpg_foreground_submissions (
                    workspace_id, session_id, submission_id, status, claim_token,
                    job_id, interaction_id, response, error, lease_expires_at,
                    execution_started_at, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP),
                    %s::timestamptz,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP),
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP)
                ) ON CONFLICT (workspace_id, session_id, submission_id) DO NOTHING
                """,
                (
                    context.workspace_id,
                    campaign_id,
                    submission.get("submission_id"),
                    submission.get("status", "completed"),
                    submission.get("claim_token") or "legacy-import",
                    job_id,
                    interaction_id,
                    _json(response) if response is not None else None,
                    submission.get("error"),
                    submission.get("lease_expires_at"),
                    submission.get("execution_started_at"),
                    submission.get("created_at"),
                    submission.get("updated_at"),
                ),
            )
        revision = int(item.get("revision", 0))
        work.connection.execute(
            """
            INSERT INTO omnix_rpg_snapshots (
                id, workspace_id, campaign_id, revision, snapshot_jsonb,
                state_hash, engine_version, schema_version
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            ON CONFLICT (campaign_id, revision) DO NOTHING
            """,
            (
                f"snapshot:legacy:{campaign_id}:{revision}",
                context.workspace_id,
                campaign_id,
                revision,
                canonical_json(dict(item.get("state") or {})),
                digest,
                engine_version,
                schema_version,
            ),
        )
