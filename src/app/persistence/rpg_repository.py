from __future__ import annotations

import hashlib
import json
from typing import Any

from .errors import EntityNotFound, RevisionConflict
from .tenant import TenantContext


MAX_COMPACT_TURN_RESPONSE_BYTES = 20_000


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def state_hash(state: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(state).encode("utf-8")).hexdigest()


def _campaign(row: Any) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "workspace_id": str(row[1]),
        "owner_user_id": str(row[2]) if row[2] is not None else None,
        "title": str(row[3]),
        "revision": int(row[4]),
        "state": dict(row[5]),
        "state_hash": str(row[6]),
        "engine_version": str(row[7]),
        "schema_version": str(row[8]),
        "seed": str(row[9]),
        "status": str(row[10]),
        "created_at": row[11].isoformat(),
        "updated_at": row[12].isoformat(),
        "metadata": dict(row[13]),
    }


_CAMPAIGN_COLUMNS = """
id, workspace_id, owner_user_id, title, revision, state_jsonb, state_hash,
engine_version, schema_version, seed, status, created_at, updated_at, metadata
"""


def _turn(row: Any) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "workspace_id": str(row[1]),
        "campaign_id": str(row[2]),
        "sequence": int(row[3]),
        "submission_id": str(row[4]),
        "expected_revision": int(row[5]),
        "resulting_revision": int(row[6]),
        "command": dict(row[7]),
        "canonical_effects": dict(row[8]),
        "state_hash_before": str(row[9]),
        "state_hash_after": str(row[10]),
        "engine_version": str(row[11]),
        "schema_version": str(row[12]),
        "interaction_id": str(row[13]),
        "compact_response": dict(row[14]),
        "created_at": row[15].isoformat(),
    }


_TURN_COLUMNS = """
id, workspace_id, campaign_id, sequence, submission_id, expected_revision,
resulting_revision, command_jsonb, canonical_effects_jsonb, state_hash_before,
state_hash_after, engine_version, schema_version, interaction_id,
compact_response, created_at
"""


class CompactTurnResponseTooLarge(ValueError):
    pass


class StateHashConflict(RevisionConflict):
    pass


class PostgresRpgRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create_campaign(
        self,
        context: TenantContext,
        *,
        campaign_id: str,
        title: str,
        state: dict[str, Any],
        engine_version: str,
        schema_version: str,
        seed: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        digest = state_hash(state)
        row = self.connection.execute(
            f"""
            INSERT INTO omnix_rpg_campaigns (
                id, workspace_id, owner_user_id, title, state_jsonb, state_hash,
                engine_version, schema_version, seed, metadata
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
            RETURNING {_CAMPAIGN_COLUMNS}
            """,
            (
                campaign_id,
                context.workspace_id,
                context.user_id,
                title,
                canonical_json(state),
                digest,
                engine_version,
                schema_version,
                seed,
                canonical_json(metadata or {}),
            ),
        ).fetchone()
        self.connection.execute(
            """
            INSERT INTO omnix_rpg_participants
                (campaign_id, user_id, role, permissions)
            VALUES (%s, %s, 'owner', ARRAY['read', 'write', 'admin'])
            ON CONFLICT DO NOTHING
            """,
            (campaign_id, context.user_id),
        )
        self._outbox(
            context,
            aggregate_id=campaign_id,
            event_type="rpg.campaign_created",
            payload={"campaign_id": campaign_id, "revision": 0, "state_hash": digest},
        )
        return _campaign(row)

    def get_campaign(
        self,
        context: TenantContext,
        campaign_id: str,
        *,
        for_update: bool = False,
    ) -> dict[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        row = self.connection.execute(
            f"SELECT {_CAMPAIGN_COLUMNS} FROM omnix_rpg_campaigns "
            f"WHERE id = %s AND workspace_id = %s{suffix}",
            (campaign_id, context.workspace_id),
        ).fetchone()
        return _campaign(row) if row is not None else None

    def list_campaigns(
        self,
        context: TenantContext,
        *,
        limit: int = 100,
        status: str = "active",
    ) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"SELECT {_CAMPAIGN_COLUMNS} FROM omnix_rpg_campaigns "
            "WHERE workspace_id = %s AND status = %s "
            "ORDER BY updated_at DESC, id DESC LIMIT %s",
            (context.workspace_id, status, max(1, min(int(limit), 500))),
        ).fetchall()
        return [_campaign(row) for row in rows]

    def get_turn_by_submission(
        self,
        context: TenantContext,
        campaign_id: str,
        submission_id: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {_TURN_COLUMNS} FROM omnix_rpg_turns "
            "WHERE workspace_id = %s AND campaign_id = %s AND submission_id = %s",
            (context.workspace_id, campaign_id, submission_id),
        ).fetchone()
        return _turn(row) if row is not None else None

    def list_turns(
        self,
        context: TenantContext,
        campaign_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"SELECT {_TURN_COLUMNS} FROM omnix_rpg_turns "
            "WHERE workspace_id = %s AND campaign_id = %s AND sequence > %s "
            "ORDER BY sequence ASC LIMIT %s",
            (
                context.workspace_id,
                campaign_id,
                int(after_sequence),
                max(1, min(int(limit), 500)),
            ),
        ).fetchall()
        return [_turn(row) for row in rows]

    def commit_turn(
        self,
        context: TenantContext,
        *,
        campaign_id: str,
        turn_id: str,
        submission_id: str,
        interaction_id: str,
        expected_revision: int,
        command: dict[str, Any],
        next_state: dict[str, Any],
        canonical_effects: dict[str, Any],
        interaction_event: dict[str, Any],
        compact_response: dict[str, Any],
        engine_version: str,
        schema_version: str,
        create_snapshot: bool = False,
        snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        encoded_response = canonical_json(compact_response).encode("utf-8")
        if not 0 < len(encoded_response) <= MAX_COMPACT_TURN_RESPONSE_BYTES:
            raise CompactTurnResponseTooLarge(
                f"compact turn response is {len(encoded_response)} bytes; "
                f"limit is {MAX_COMPACT_TURN_RESPONSE_BYTES}"
            )

        campaign = self.get_campaign(context, campaign_id, for_update=True)
        if campaign is None:
            raise EntityNotFound(campaign_id)

        existing = self.get_turn_by_submission(context, campaign_id, submission_id)
        if existing is not None:
            return {"idempotent_replay": True, "campaign": campaign, "turn": existing}

        if campaign["revision"] != expected_revision:
            raise RevisionConflict(
                f"campaign {campaign_id} expected revision {expected_revision}; "
                f"current {campaign['revision']}"
            )
        before_hash = campaign["state_hash"]
        calculated_before = state_hash(campaign["state"])
        if before_hash != calculated_before:
            raise StateHashConflict(
                f"campaign {campaign_id} stored state hash does not match authoritative state"
            )

        resulting_revision = expected_revision + 1
        sequence = resulting_revision
        after_hash = state_hash(next_state)
        row = self.connection.execute(
            f"""
            INSERT INTO omnix_rpg_turns (
                id, workspace_id, campaign_id, sequence, submission_id,
                expected_revision, resulting_revision, command_jsonb,
                canonical_effects_jsonb, state_hash_before, state_hash_after,
                engine_version, schema_version, interaction_id, compact_response
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                %s, %s, %s, %s, %s, %s::jsonb
            ) RETURNING {_TURN_COLUMNS}
            """,
            (
                turn_id,
                context.workspace_id,
                campaign_id,
                sequence,
                submission_id,
                expected_revision,
                resulting_revision,
                canonical_json(command),
                canonical_json(canonical_effects),
                before_hash,
                after_hash,
                engine_version,
                schema_version,
                interaction_id,
                encoded_response.decode("utf-8"),
            ),
        ).fetchone()
        turn = _turn(row)

        updated = self.connection.execute(
            f"""
            UPDATE omnix_rpg_campaigns
               SET state_jsonb = %s::jsonb,
                   state_hash = %s,
                   revision = %s,
                   engine_version = %s,
                   schema_version = %s,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s AND revision = %s
            RETURNING {_CAMPAIGN_COLUMNS}
            """,
            (
                canonical_json(next_state),
                after_hash,
                resulting_revision,
                engine_version,
                schema_version,
                campaign_id,
                context.workspace_id,
                expected_revision,
            ),
        ).fetchone()
        if updated is None:
            raise RevisionConflict(f"campaign changed while committing turn: {campaign_id}")
        updated_campaign = _campaign(updated)

        self.connection.execute(
            """
            INSERT INTO omnix_rpg_interactions (
                interaction_id, workspace_id, campaign_id, turn_id, sequence,
                state_revision, event_jsonb
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                interaction_id,
                context.workspace_id,
                campaign_id,
                turn_id,
                sequence,
                resulting_revision,
                canonical_json(interaction_event),
            ),
        )

        snapshot: dict[str, Any] | None = None
        if create_snapshot:
            snapshot = self.create_snapshot(
                context,
                campaign_id=campaign_id,
                snapshot_id=snapshot_id or f"snapshot:{campaign_id}:{resulting_revision}",
                revision=resulting_revision,
                state=next_state,
                state_hash_value=after_hash,
                engine_version=engine_version,
                schema_version=schema_version,
            )

        self._outbox(
            context,
            aggregate_id=campaign_id,
            event_type="rpg.turn_committed",
            payload={
                "campaign_id": campaign_id,
                "turn_id": turn_id,
                "submission_id": submission_id,
                "interaction_id": interaction_id,
                "sequence": sequence,
                "resulting_revision": resulting_revision,
                "state_hash": after_hash,
            },
        )
        return {
            "idempotent_replay": False,
            "campaign": updated_campaign,
            "turn": turn,
            "snapshot": snapshot,
        }

    def create_snapshot(
        self,
        context: TenantContext,
        *,
        campaign_id: str,
        snapshot_id: str,
        revision: int,
        state: dict[str, Any],
        state_hash_value: str,
        engine_version: str,
        schema_version: str,
    ) -> dict[str, Any]:
        calculated = state_hash(state)
        if calculated != state_hash_value:
            raise StateHashConflict("snapshot state hash does not match snapshot state")
        row = self.connection.execute(
            """
            INSERT INTO omnix_rpg_snapshots (
                id, workspace_id, campaign_id, revision, snapshot_jsonb,
                state_hash, engine_version, schema_version
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            RETURNING id, campaign_id, revision, snapshot_jsonb, state_hash,
                      engine_version, schema_version, created_at
            """,
            (
                snapshot_id,
                context.workspace_id,
                campaign_id,
                revision,
                canonical_json(state),
                state_hash_value,
                engine_version,
                schema_version,
            ),
        ).fetchone()
        return {
            "id": str(row[0]),
            "campaign_id": str(row[1]),
            "revision": int(row[2]),
            "state": dict(row[3]),
            "state_hash": str(row[4]),
            "engine_version": str(row[5]),
            "schema_version": str(row[6]),
            "created_at": row[7].isoformat(),
        }

    def _outbox(
        self,
        context: TenantContext,
        *,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> int:
        row = self.connection.execute(
            """
            INSERT INTO omnix_outbox_events (
                workspace_id, aggregate_type, aggregate_id, event_type,
                ordering_key, payload
            ) VALUES (%s, 'rpg_campaign', %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                context.workspace_id,
                aggregate_id,
                event_type,
                aggregate_id,
                canonical_json(payload),
            ),
        ).fetchone()
        return int(row[0])
