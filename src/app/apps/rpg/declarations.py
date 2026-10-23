"""What the kernel reads about the RPG module without loading it (ADR-0016, PA-2.2): kernel imports only."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.persistence.declarations import (
    CapacityCount,
    LegacyImport,
    RecordOnlyJobGuard,
    RetentionDeclaration,
    SettingsSection,
)


def _delete_narration_events(connection: Any, retention_days: int, batch_size: int) -> int:
    return int(connection.execute(
        """
        DELETE FROM omnix_rpg_narration_events
         WHERE event_id IN (
             SELECT event_id
               FROM omnix_rpg_narration_events
              WHERE created_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
              ORDER BY created_at, event_id
              LIMIT %s
         )
        """,
        (max(1, int(retention_days)), max(1, int(batch_size))),
    ).rowcount)


SNAPSHOTS_KEPT_PER_CAMPAIGN = 20
SNAPSHOT_KEPT_EVERY_REVISIONS = 100


def _delete_snapshots(connection: Any, retention_days: int, batch_size: int) -> int:
    """Snapshots outside each campaign's newest 20 and not at a 100th revision (WP-5.2).

    ``retention_days`` is a grace period: a snapshot is kept at least that long.
    Blob-backed snapshots are left to their asset's lifecycle, and pinned ones
    (a pre-upgrade backup, an upcast boundary: RQ-1.7) are never deleted.
    """
    return int(connection.execute(
        """
        DELETE FROM omnix_rpg_snapshots
         WHERE id IN (
             SELECT id
               FROM (SELECT id, revision, created_at, blob_asset_id, pinned,
                            row_number() OVER (PARTITION BY campaign_id ORDER BY revision DESC) AS newest
                       FROM omnix_rpg_snapshots) AS ranked
              WHERE newest > %s
                AND revision %% %s <> 0
                AND blob_asset_id IS NULL
                AND NOT pinned
                AND created_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
              ORDER BY created_at, id
              LIMIT %s
         )
        """,
        (SNAPSHOTS_KEPT_PER_CAMPAIGN, SNAPSHOT_KEPT_EVERY_REVISIONS, max(1, int(retention_days)), max(1, int(batch_size))),
    ).rowcount)


COMPACT_CAMPAIGNS_ABOVE_REVISIONS = 5_000
COMPACTION_KEEPS_REVISIONS = 1_000


def _delete_archived_campaigns(connection: Any, retention_days: int, batch_size: int) -> int:
    """Campaigns deleted (archived) longer ago than the grace period go, with everything of theirs (RQ-8.10).

    Every RPG table holding a campaign's rows cascades from the campaign row: its turns,
    interactions, snapshots, narration, maps and NPC runtime, so the player's text goes too.
    """
    return int(connection.execute(
        """
        DELETE FROM omnix_rpg_campaigns
         WHERE id IN (
             SELECT id
               FROM omnix_rpg_campaigns
              WHERE status = 'archived'
                AND updated_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
              ORDER BY updated_at, id
              LIMIT %s
         )
        """,
        (max(1, int(retention_days)), max(1, int(batch_size))),
    ).rowcount)


def _compact_long_campaigns(connection: Any, retention_days: int, batch_size: int) -> int:
    """Fold a long campaign's old turns into a pinned snapshot, then delete them (RQ-8.10, owner decision Q-9).

    Only campaigns past 5,000 revisions are compacted. The base is the newest full snapshot at least
    1,000 revisions old; it is pinned, so replay starts there, and the turns, interactions,
    narration and unpinned snapshots before it are deleted. Smaller campaigns keep every turn.
    ``retention_days`` is unused: the threshold is a revision count, not an age.
    """
    del retention_days
    campaigns = connection.execute(
        """
        SELECT campaign.id, snapshot.revision
          FROM omnix_rpg_campaigns AS campaign
          JOIN LATERAL (
                SELECT revision
                  FROM omnix_rpg_snapshots
                 WHERE campaign_id = campaign.id
                   AND snapshot_jsonb IS NOT NULL
                   AND revision <= campaign.revision - %s
                 ORDER BY revision DESC
                 LIMIT 1
          ) AS snapshot ON TRUE
         WHERE campaign.revision > %s
           AND EXISTS (SELECT 1 FROM omnix_rpg_turns
                        WHERE campaign_id = campaign.id AND resulting_revision <= snapshot.revision)
         ORDER BY campaign.id
         LIMIT %s
        """,
        (COMPACTION_KEEPS_REVISIONS, COMPACT_CAMPAIGNS_ABOVE_REVISIONS, max(1, int(batch_size))),
    ).fetchall()
    deleted = 0
    for campaign_id, base in campaigns:
        connection.execute(
            "UPDATE omnix_rpg_snapshots SET pinned = true WHERE campaign_id = %s AND revision = %s",
            (campaign_id, base),
        )
        deleted += int(connection.execute(
            "DELETE FROM omnix_rpg_narrative_responses WHERE campaign_id = %s AND revision <= %s",
            (campaign_id, base),
        ).rowcount)
        # Interactions cascade from their turn.
        deleted += int(connection.execute(
            "DELETE FROM omnix_rpg_turns WHERE campaign_id = %s AND resulting_revision <= %s",
            (campaign_id, base),
        ).rowcount)
        deleted += int(connection.execute(
            "DELETE FROM omnix_rpg_snapshots WHERE campaign_id = %s AND revision < %s AND NOT pinned",
            (campaign_id, base),
        ).rowcount)
    return deleted


def _count(table: str) -> Any:
    def count(connection: Any) -> int:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    return count


RETENTION = (
    RetentionDeclaration("rpg_narration_events", delete=_delete_narration_events, capacity_cleanup=True),
    RetentionDeclaration("rpg_snapshots", delete=_delete_snapshots),
    RetentionDeclaration("rpg_archived_campaigns", delete=_delete_archived_campaigns),
    RetentionDeclaration("rpg_turn_compaction", delete=_compact_long_campaigns),
)
CAPACITY = (
    CapacityCount("rpg_turns", count=_count("omnix_rpg_turns")),
    CapacityCount("rpg_narration_events", count=_count("omnix_rpg_narration_events")),
    CapacityCount("rpg_snapshots", count=_count("omnix_rpg_snapshots")),
)


class RpgSettingsProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    difficulty: str = "normal"
    world_activity: str = Field("standard", alias="worldActivity")
    economy_pressure: str = Field("normal", alias="economyPressure")
    combat_lethality: str = Field("normal", alias="combatLethality")
    companions: bool = True
    permadeath: bool = False
    autosave: bool = True
    validator: bool = True
    background_soft_audit: bool = Field(True, alias="backgroundSoftAudit")
    llm_narration: bool = Field(True, alias="llmNarration")
    image_generation: bool = Field(False, alias="imageGeneration")
    tts: bool = False
    stt: bool = False
    campaign_defaults: dict[str, Any] = Field(default_factory=dict, alias="campaignDefaults")
    hermes_assist_mode: str = Field("review_each_step", alias="hermesAssistMode")


SETTINGS = (SettingsSection("rpg", RpgSettingsProfile, order=40),)


def _restore_campaign(work: Any, context: Any, stable_id: str, item: dict[str, Any]) -> None:
    """A legacy campaign and its owner as participant (PA-2.2)."""
    from app.persistence.cutover import canonical_json, state_hash

    state = dict(item.get("state") or {})
    digest = str(item.get("state_hash") or state_hash(state))
    revision = int(item.get("revision", 0))
    work.connection.execute(
        """
        INSERT INTO omnix_rpg_campaigns (
            id, workspace_id, owner_user_id, title, revision, state_jsonb,
            state_hash, engine_version, schema_version, seed, status, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            stable_id,
            context.workspace_id,
            context.user_id,
            item.get("title", stable_id),
            revision,
            canonical_json(state),
            digest,
            item.get("engine_version", "legacy"),
            item.get("schema_version", "legacy"),
            str(item.get("seed") or "legacy"),
            item.get("status", "active"),
            canonical_json({**dict(item.get("metadata") or {}), "legacy_import": True}),
        ),
    )
    work.connection.execute(
        """
        INSERT INTO omnix_rpg_participants
            (campaign_id, user_id, role, permissions)
        VALUES (%s, %s, 'owner', ARRAY['read', 'write', 'admin'])
        """,
        (stable_id, context.user_id),
    )


def _restore_history(work: Any, context: Any, campaign_id: str, item: dict[str, Any]) -> None:
    """A legacy campaign's turns, interactions, foreground submissions and snapshot (PA-2.2)."""
    from app.persistence.cutover import canonical_json, state_hash

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
            if not work.jobs.job_exists(str(job_id)):
                job_id = None
        response = submission.get("response")
        response_interaction_id = None
        if isinstance(response, dict):
            response_interaction_id = response.get("interaction_id")
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
                response_interaction_id,
                canonical_json(response) if response is not None else None,
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


LEGACY_IMPORTS = (
    LegacyImport("rpg.campaign", _restore_campaign),
    LegacyImport("rpg.history", _restore_history),
)

# Only the session's claimed foreground submission may move its record-only turn job.
RECORD_ONLY_JOB_GUARDS = (
    RecordOnlyJobGuard(
        "rpg.turn.foreground_record",
        """        AND module = 'rpg'
        AND metadata #> '{compat_contract,compat,record_only}' = 'true'::jsonb
        AND EXISTS (
            SELECT 1 FROM omnix_rpg_foreground_submissions AS submission
             WHERE submission.workspace_id = {job}.workspace_id
               AND submission.job_id = {job}.id
               AND submission.session_id = {job}.metadata #>> '{compat_contract,input_ref,session_id}'
               AND submission.submission_id = {job}.input_payload ->> 'submission_id'
               AND submission.claim_token = %s
               AND submission.status = 'claimed'
               AND submission.execution_started_at IS NOT NULL
        )""",
    ),
)
