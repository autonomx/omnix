from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping

from app.apps.rpg.foundation.persistence.document_parts import (
    StoredForm,
    assembled,
    canonical_json,
    hash_matches,
    state_hash,
    stored_document,
    stored_form,
)
from app.apps.rpg.foundation.safe_values import copy_state
from app.apps.rpg.foundation.persistence.turn_narrations import split_turn_narrations
from app.persistence.errors import EntityNotFound, RevisionConflict
from app.persistence.tenant import TenantContext
from app.runtime.pagination import MAX_PAGE_SIZE, page_limit


MAX_COMPACT_TURN_RESPONSE_BYTES = 20_000


def document_version(state: Any) -> int | None:
    """The campaign document's version (``manifest.schema_version``), as turn rows and snapshots record it."""
    manifest = state.get("manifest") if isinstance(state, dict) else None
    value = manifest.get("schema_version") if isinstance(manifest, dict) else None
    try:
        return int(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


_document_version_of = document_version  # for the methods whose parameter of that name shadows it


def _campaign(row: Any, *, state: dict[str, Any] | None = None, part_hashes: dict[str, str] | None = None) -> dict[str, Any]:
    """A campaign row; its ``state`` assembled from its head and parts (``_CAMPAIGN_COLUMNS``), or the one given (a
    commit's, with its parts' hashes)."""
    if state is None:
        state, part_hashes = assembled(dict(row[5]), row[14])
    return {
        "id": str(row[0]),
        "workspace_id": str(row[1]),
        "owner_user_id": str(row[2]) if row[2] is not None else None,
        "title": str(row[3]),
        "revision": int(row[4]),
        "state": state,
        "part_hashes": dict(part_hashes or {}),
        "state_hash": str(row[6]),
        "engine_version": str(row[7]),
        "schema_version": str(row[8]),
        "seed": str(row[9]),
        "status": str(row[10]),
        "created_at": row[11].isoformat(),
        "updated_at": row[12].isoformat(),
        "metadata": dict(row[13]),
    }


# Top-level state keys a session list row carries (``app.apps.rpg.session.list_summaries``).
SESSION_SUMMARY_STATE_KEYS = (
    "location",
    "current_location",
    "current_location_id",
    "current_location_name",
    "published_world",
    "environment_snapshot",
)

# A campaign row's parts as one object, {path: [hash, value]} (``assembled``; Q-13). JSON, not JSONB: each part's
# text is written out as it is, where a JSONB aggregate rebuilds every part first.
CAMPAIGN_PARTS = """(SELECT json_object_agg(part.path, json_build_array(part.part_hash, part.part_jsonb))
   FROM omnix_rpg_campaign_parts AS part
  WHERE part.workspace_id = omnix_rpg_campaigns.workspace_id AND part.campaign_id = omnix_rpg_campaigns.id)"""
_CAMPAIGN_COLUMNS = f"""
id, workspace_id, owner_user_id, title, revision, state_jsonb, state_hash,
engine_version, schema_version, seed, status, created_at, updated_at, metadata,
{CAMPAIGN_PARTS}
"""
# The row, its document left out when its revision and hash are the ones this process keeps (four parameters, first).
_CAMPAIGN_COLUMNS_UNLESS_KEPT = f"""
id, workspace_id, owner_user_id, title, revision,
CASE WHEN revision = %s AND state_hash = %s THEN NULL ELSE state_jsonb END, state_hash,
engine_version, schema_version, seed, status, created_at, updated_at, metadata,
CASE WHEN revision = %s AND state_hash = %s THEN NULL ELSE {CAMPAIGN_PARTS} END
"""


# The campaign document each campaign last had in this process, as stored (F2): a turn reads its campaign at its load
# and again under its commit's lock, a megabyte each time at 1 MB. A read whose row still has the kept revision and
# hash gets the kept document, and the database sends none; the hash is of the content, so a kept document is the
# stored one. A commit keeps the document it wrote. The kept document is never handed out to change: a reader gets a
# copy, the commit (which only reads it) the document itself.
@dataclass(frozen=True)
class _Kept:
    revision: int
    state_hash: str
    document: dict[str, Any]
    part_hashes: dict[str, str]
    at: float


_KEPT: OrderedDict[tuple[str, str], _Kept] = OrderedDict()
_KEPT_LOCK = threading.Lock()
_MAX_KEPT = 16
_KEPT_TTL_SECONDS = 900.0


def clear_kept_documents() -> None:
    """Forget the kept campaign documents (each is read whole when next asked for)."""
    with _KEPT_LOCK:
        _KEPT.clear()


def _kept(key: tuple[str, str]) -> _Kept | None:
    with _KEPT_LOCK:
        kept = _KEPT.get(key)
        if kept is not None and time.monotonic() - kept.at > _KEPT_TTL_SECONDS:
            _KEPT.pop(key, None)
            return None
        if kept is not None:
            _KEPT.move_to_end(key)
        return kept


def _keep(key: tuple[str, str], revision: int, digest: str, document: dict[str, Any] | None,
          part_hashes: Mapping[str, str]) -> None:
    with _KEPT_LOCK:
        if document is None:
            _KEPT.pop(key, None)
            return
        _KEPT[key] = _Kept(revision, digest, document, dict(part_hashes), time.monotonic())
        _KEPT.move_to_end(key)
        while len(_KEPT) > _MAX_KEPT:
            _KEPT.popitem(last=False)


# A written row's columns, its state left out (the writer has it): ``_campaign(row, state=...)``.
_CAMPAIGN_ROW_COLUMNS = """
id, workspace_id, owner_user_id, title, revision, NULL, state_hash,
engine_version, schema_version, seed, status, created_at, updated_at, metadata
"""
# What a write does to the campaign's parts (Q-13): the changed ones upserted, the ones no longer parts deleted. A
# prefix (``WITH``), so a turn's commit writes its parts in the statement that writes its head.
_PARTS_WRITE = """
WITH written_parts AS (
    INSERT INTO omnix_rpg_campaign_parts (workspace_id, campaign_id, path, part_hash, part_jsonb)
    SELECT %s, %s, part.key, part.value ->> 0, part.value -> 1 FROM jsonb_each(%s::jsonb) AS part
    ON CONFLICT (workspace_id, campaign_id, path) DO UPDATE
       SET part_hash = EXCLUDED.part_hash, part_jsonb = EXCLUDED.part_jsonb
    RETURNING 1
), removed_parts AS (
    DELETE FROM omnix_rpg_campaign_parts
     WHERE workspace_id = %s AND campaign_id = %s AND path = ANY(%s::text[])
    RETURNING 1
)
"""


def _parts_params(context: TenantContext, campaign_id: str, form: StoredForm) -> tuple[Any, ...]:
    # The written parts as one object, {path: [hash, value]}, made of the texts already serialized.
    written = ",".join(f"{json.dumps(path)}:[{json.dumps(digest)},{text}]"
                       for path, (text, digest) in sorted(form.written.items()))
    return (context.workspace_id, campaign_id, "{" + written + "}", context.workspace_id, campaign_id,
            list(form.removed))


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
        "state_delta": list(row[16]) if row[16] is not None else None,
        "maps_hash_after": str(row[17]) if row[17] is not None else None,
    }


_TURN_COLUMNS = """
id, workspace_id, campaign_id, sequence, submission_id, expected_revision,
resulting_revision, command_jsonb, canonical_effects_jsonb, state_hash_before,
state_hash_after, engine_version, schema_version, interaction_id,
compact_response, created_at, state_delta_jsonb, maps_hash_after
"""


def _turn_delta(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    from .state_delta import state_delta

    return state_delta(before, after)


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
        form = stored_form(state)
        row = self.connection.execute(
            f"""
            INSERT INTO omnix_rpg_campaigns (
                id, workspace_id, owner_user_id, title, state_jsonb, state_hash,
                engine_version, schema_version, seed, metadata
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
            RETURNING {_CAMPAIGN_ROW_COLUMNS}
            """,
            (
                campaign_id,
                context.workspace_id,
                context.user_id,
                title,
                form.head,
                form.digest,
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
        self.write_parts(context, campaign_id, form)
        return _campaign(row, state=state, part_hashes=form.part_hashes)

    def write_parts(self, context: TenantContext, campaign_id: str, form: StoredForm) -> None:
        """Store what ``form`` changed of the campaign's parts (Q-13); its head is the caller's to write."""
        if form.written or form.removed:
            self.connection.execute(_PARTS_WRITE + "SELECT 1", _parts_params(context, campaign_id, form))

    def get_campaign(
        self,
        context: TenantContext,
        campaign_id: str,
        *,
        for_update: bool = False,
        read_only: bool = False,
    ) -> dict[str, Any] | None:
        """The campaign; ``read_only``: the caller never changes its ``state`` (a commit), so a kept document is not
        copied for it."""
        suffix = " FOR UPDATE" if for_update else ""
        key = (context.workspace_id, campaign_id)
        kept = _kept(key)
        version = (kept.revision, kept.state_hash) if kept is not None else (-1, "")
        row = self.connection.execute(
            f"SELECT {_CAMPAIGN_COLUMNS_UNLESS_KEPT} FROM omnix_rpg_campaigns "
            f"WHERE id = %s AND workspace_id = %s{suffix}",
            (*version, *version, campaign_id, context.workspace_id),
        ).fetchone()
        if row is None:
            return None
        if row[5] is None and kept is not None:  # still the kept revision and hash: the database sent no document
            return _campaign(row, state=kept.document if read_only else copy_state(kept.document),
                             part_hashes=kept.part_hashes)
        state, part_hashes = assembled(dict(row[5]), row[14])
        _keep(key, int(row[4]), str(row[6]), state if read_only else copy_state(state), part_hashes)
        return _campaign(row, state=state, part_hashes=part_hashes)

    def lock_campaign(self, context: TenantContext, campaign_id: str) -> bool:
        """Lock the campaign row ``FOR UPDATE`` without reading its state; False when there is none."""
        row = self.connection.execute(
            "SELECT 1 FROM omnix_rpg_campaigns WHERE id = %s AND workspace_id = %s FOR UPDATE",
            (campaign_id, context.workspace_id),
        ).fetchone()
        return row is not None

    def launch_gate_source(self, context: TenantContext, campaign_id: str) -> dict[str, Any] | None:
        """What the launch-readiness gate reads of the state, without decoding the saved game.

        ``campaign_launch_readiness`` asks whether the setup's world forge is a
        non-empty object, whether the state has a (truthy) campaign bible, and
        reads the runtime's launch gate; the truthiness is evaluated here. The turn route also reads
        whether the campaign has ended (a hardcore defeat, RQ-5.1).
        """
        row = self.connection.execute(
            """
            SELECT COALESCE(jsonb_typeof(state_jsonb #> '{setup_payload,world_forge}') = 'object'
                            AND state_jsonb #> '{setup_payload,world_forge}' <> '{}'::jsonb, FALSE),
                   COALESCE(state_jsonb #> '{state,campaign_bible}' NOT IN
                            ('null'::jsonb, 'false'::jsonb, '0'::jsonb, '""'::jsonb, '{}'::jsonb, '[]'::jsonb), FALSE),
                   state_jsonb #> '{runtime_state,campaign_launch_gate}',
                   state_jsonb #> '{simulation_state,campaign_end}'
              FROM omnix_rpg_campaigns WHERE id = %s AND workspace_id = %s
            """,
            (campaign_id, context.workspace_id),
        ).fetchone()
        if row is None:
            return None
        gate = row[2] if isinstance(row[2], dict) else {}
        return {
            "setup_payload": {"world_forge": {"enabled": True} if row[0] else {}},
            "state": {"campaign_bible": True if row[1] else None},
            "runtime_state": {"campaign_launch_gate": dict(gate)},
            "simulation_state": {"campaign_end": dict(row[3]) if isinstance(row[3], dict) else {}},
        }

    def stored_version(self, context: TenantContext, campaign_id: str) -> tuple[int, str] | None:
        """The campaign's stored (revision, state_hash), without its state."""
        row = self.connection.execute(
            "SELECT revision, state_hash FROM omnix_rpg_campaigns WHERE id = %s AND workspace_id = %s",
            (campaign_id, context.workspace_id),
        ).fetchone()
        return (int(row[0]), str(row[1])) if row is not None else None

    def stored_rng_seed(self, context: TenantContext, campaign_id: str) -> tuple[bool, Any]:
        """Whether the campaign exists, and its stored ``simulation_state.rng_seed`` (without loading the state)."""
        row = self.connection.execute(
            "SELECT state_jsonb #> '{simulation_state,rng_seed}' FROM omnix_rpg_campaigns WHERE id = %s AND workspace_id = %s",
            (campaign_id, context.workspace_id),
        ).fetchone()
        return (row is not None, row[0] if row is not None else None)

    def list_campaigns(
        self,
        context: TenantContext,
        *,
        limit: int = 100,
        status: str = "active",
        before: tuple[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """One page, newest first; pass the last row's ``(updated_at, id)`` as ``before``."""
        rows = self.connection.execute(
            f"SELECT {_CAMPAIGN_COLUMNS} FROM omnix_rpg_campaigns "
            "WHERE workspace_id = %s AND status = %s "
            "AND (%s::timestamptz IS NULL OR (updated_at, id) < (%s::timestamptz, %s::text)) "
            "ORDER BY updated_at DESC, id DESC LIMIT %s",
            (
                context.workspace_id,
                status,
                before[0] if before else None,
                before[0] if before else None,
                before[1] if before else None,
                page_limit(limit, default=100),
            ),
        ).fetchall()
        return [_campaign(row) for row in rows]

    def list_campaign_summary_sources(
        self,
        context: TenantContext,
        *,
        limit: int = 100,
        status: str = "active",
        before: tuple[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """One page of campaigns, newest first, each with only what a list row reads.

        ``source`` keeps the session document's shape (``manifest``, and of
        ``state`` the world and region environments, the scene's environment
        context and the opening location keys). A trigger keeps it in
        ``summary_jsonb`` with the turn count, player level and location name
        on every state write (migration 0157), so a list never reads a saved
        game's state.
        """
        rows = self.connection.execute(
            """
            SELECT id, updated_at, summary_jsonb, turn_count, player_level, location_name
              FROM omnix_rpg_campaigns
             WHERE workspace_id = %s AND status = %s
               AND (%s::timestamptz IS NULL OR (updated_at, id) < (%s::timestamptz, %s::text))
             ORDER BY updated_at DESC, id DESC LIMIT %s
            """,
            (
                context.workspace_id,
                status,
                before[0] if before else None,
                before[0] if before else None,
                before[1] if before else None,
                page_limit(limit, default=100),
            ),
        ).fetchall()
        return [
            {
                "id": str(row[0]),
                "updated_at": row[1].isoformat(),
                "source": dict(row[2]),
                "turn_count": row[3],
                "player_level": row[4],
                "location_name": row[5],
            }
            for row in rows
        ]

    def iter_campaigns(self, context: TenantContext, *, status: str = "active"):
        """Every campaign with ``status``, newest first, a page at a time."""
        before: tuple[str, str] | None = None
        while True:
            page = self.list_campaigns(context, limit=MAX_PAGE_SIZE, status=status, before=before)
            yield from page
            if len(page) < MAX_PAGE_SIZE:
                return
            before = (page[-1]["updated_at"], page[-1]["id"])

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
        locked_campaign: dict[str, Any] | None = None,
        submission_open: bool = False,
        maps_touched: bool | None = None,
    ) -> dict[str, Any]:
        """Commit one turn. ``locked_campaign`` is the row the caller already read ``FOR UPDATE`` in this transaction.

        ``submission_open``: the caller holds the submission's claim, still open, in this transaction; a turn commits
        with its claim completed, so no turn of this submission exists and none is looked for. ``maps_touched``: whether
        this transaction changed a map instance (None: find out).
        """
        encoded_response = canonical_json(compact_response).encode("utf-8")
        if not 0 < len(encoded_response) <= MAX_COMPACT_TURN_RESPONSE_BYTES:
            raise CompactTurnResponseTooLarge(
                f"compact turn response is {len(encoded_response)} bytes; "
                f"limit is {MAX_COMPACT_TURN_RESPONSE_BYTES}"
            )

        campaign = locked_campaign if locked_campaign is not None else self.get_campaign(context, campaign_id, for_update=True)
        if campaign is None or campaign["id"] != campaign_id:
            raise EntityNotFound(campaign_id)

        existing = None if submission_open else self.get_turn_by_submission(context, campaign_id, submission_id)
        if existing is not None:  # the campaign as read (it may be the kept document): a copy goes out
            return {"idempotent_replay": True, "campaign": {**campaign, "state": copy_state(campaign["state"])},
                    "turn": existing}
        # The turns' narrations are kept beside the document, not in it (RQ-1.4).
        next_state, narrations = split_turn_narrations(dict(next_state))

        if campaign["revision"] != expected_revision:
            raise RevisionConflict(
                f"campaign {campaign_id} expected revision {expected_revision}; "
                f"current {campaign['revision']}"
            )
        # The row's state and hash are always written together, and the commit
        # is conditional on the revision: re-hashing the stored state (a full
        # canonical serialization) on every turn caught only out-of-band edits
        # to the row (WP-5.6). Snapshots still verify the hash they store.
        before_hash = campaign["state_hash"]

        resulting_revision = expected_revision + 1
        sequence = resulting_revision
        # Only what changed is serialized, hashed and written: the parts the turn left as they were keep their stored
        # text and hashes (Q-13).
        form = stored_form(next_state, before=campaign["state"], stored_parts=campaign.get("part_hashes"))
        after_hash = form.digest
        row = self.connection.execute(
            f"""
            INSERT INTO omnix_rpg_turns (
                id, workspace_id, campaign_id, sequence, submission_id,
                expected_revision, resulting_revision, command_jsonb,
                canonical_effects_jsonb, state_hash_before, state_hash_after,
                engine_version, schema_version, interaction_id, compact_response,
                state_delta_jsonb, document_version, maps_hash_after
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s
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
                canonical_json(_turn_delta(campaign["state"], next_state)),
                document_version(next_state),
                self.touched_maps_hash(context, campaign_id) if maps_touched is not False else None,
            ),
        ).fetchone()
        turn = _turn(row)

        updated = self.connection.execute(
            _PARTS_WRITE + f"""
            UPDATE omnix_rpg_campaigns
               SET state_jsonb = %s::jsonb,
                   state_hash = %s,
                   revision = %s,
                   engine_version = %s,
                   schema_version = %s,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s AND revision = %s
            RETURNING {_CAMPAIGN_ROW_COLUMNS}
            """,
            (
                *_parts_params(context, campaign_id, form),
                form.head,
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
        updated_campaign = _campaign(updated, state=next_state, part_hashes=form.part_hashes)
        # The document as now stored, kept for the next turn's reads: what the commit wrote, and the parts it left.
        _keep((context.workspace_id, campaign_id), resulting_revision, after_hash,
              stored_document(form, campaign["state"]), form.part_hashes)
        self.put_turn_narrations(context, campaign_id=campaign_id, narrations=narrations)

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
                hash_computed=True,
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
        pinned: bool = False,
        document_version: int | None = None,
        hash_computed: bool = False,
    ) -> dict[str, Any]:
        """A ``pinned`` snapshot is never deleted by retention (RQ-1.7). ``hash_computed``: the caller has just
        computed ``state_hash_value`` from ``state`` (a commit), so it is not checked again."""
        encoded = canonical_json(state)
        if document_version is None:
            document_version = _document_version_of(state)
        if not hash_computed and not hash_matches(state, state_hash_value):
            raise StateHashConflict("snapshot state hash does not match snapshot state")
        row = self.connection.execute(
            """
            INSERT INTO omnix_rpg_snapshots (
                id, workspace_id, campaign_id, revision, snapshot_jsonb,
                state_hash, engine_version, schema_version, pinned, document_version
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
            RETURNING id, campaign_id, revision, snapshot_jsonb, state_hash,
                      engine_version, schema_version, created_at
            """,
            (
                snapshot_id,
                context.workspace_id,
                campaign_id,
                revision,
                encoded,
                state_hash_value,
                engine_version,
                schema_version,
                pinned,
                document_version,
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

    def recent_turns_by_owner(self, context: TenantContext, *, window_seconds: int) -> tuple[int, Any]:
        """How many turns the caller's own campaigns committed in the window, and the oldest one's time."""
        row = self.connection.execute(
            """
            SELECT count(*), min(turn.created_at)
              FROM omnix_rpg_turns AS turn
              JOIN omnix_rpg_campaigns AS campaign
                ON campaign.id = turn.campaign_id AND campaign.workspace_id = turn.workspace_id
             WHERE turn.workspace_id = %s
               AND campaign.owner_user_id = %s
               AND turn.created_at > CURRENT_TIMESTAMP - make_interval(secs => %s)
            """,
            (context.workspace_id, context.user_id, max(1, int(window_seconds))),
        ).fetchone()
        return int(row[0] or 0), row[1]

    def document_at_revision(self, context: TenantContext, campaign_id: str, revision: int) -> dict[str, Any] | None:
        """The campaign's stored document as it stood at ``revision`` (RQ-5.7): the nearest snapshot at or before it,
        then each turn's patch, every step checked against the turn's recorded hashes. None when the history cannot
        rebuild it (a missing patch, a broken chain)."""
        from app.apps.rpg.foundation.persistence.state_delta import apply_state_delta

        snapshot = self.connection.execute(
            """
            SELECT revision, snapshot_jsonb, state_hash FROM omnix_rpg_snapshots
             WHERE workspace_id = %s AND campaign_id = %s AND revision <= %s AND snapshot_jsonb IS NOT NULL
             ORDER BY revision DESC LIMIT 1
            """,
            (context.workspace_id, campaign_id, int(revision)),
        ).fetchone()
        if snapshot is None or not hash_matches(dict(snapshot[1]), str(snapshot[2])):
            return None
        state, at, digest = dict(snapshot[1]), int(snapshot[0]), str(snapshot[2])
        for resulting, delta, before, after in self.connection.execute(
            """
            SELECT resulting_revision, state_delta_jsonb, state_hash_before, state_hash_after FROM omnix_rpg_turns
             WHERE workspace_id = %s AND campaign_id = %s AND resulting_revision > %s AND resulting_revision <= %s
             ORDER BY resulting_revision
            """,
            (context.workspace_id, campaign_id, at, int(revision)),
        ).fetchall():
            if int(resulting) != at + 1 or delta is None or str(before) != digest:
                return None
            state = apply_state_delta(state, list(delta))
            if not hash_matches(state, str(after)):
                return None
            at, digest = int(resulting), str(after)
        return state if at == int(revision) else None

    def keep_snapshot(self, context: TenantContext, *, campaign_id: str, revision: int, state: dict[str, Any],
                      engine_version: str, schema_version: str) -> None:
        """The document of a revision no turn row patches (a campaign's first, an edit outside a turn) kept as its
        snapshot, so the campaign's history can rebuild every revision (rewind.md, the replay audit)."""
        self.connection.execute(
            """
            INSERT INTO omnix_rpg_snapshots (
                id, workspace_id, campaign_id, revision, snapshot_jsonb, state_hash, engine_version, schema_version,
                document_version
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (f"snapshot:{campaign_id}:{int(revision)}", context.workspace_id, campaign_id, int(revision),
             canonical_json(state), state_hash(state), engine_version, schema_version, _document_version_of(state)),
        )

    def turn_history(self, context: TenantContext, campaign_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        """The campaign's latest turns, newest first: each one's revisions and command (what an undo walks back)."""
        rows = self.connection.execute(
            """
            SELECT resulting_revision, expected_revision, command_jsonb FROM omnix_rpg_turns
             WHERE workspace_id = %s AND campaign_id = %s ORDER BY resulting_revision DESC LIMIT %s
            """,
            (context.workspace_id, campaign_id, max(1, int(limit))),
        ).fetchall()
        return [{"resulting_revision": int(row[0]), "expected_revision": int(row[1]), "command": dict(row[2] or {})}
                for row in rows]

    def put_save_point(self, context: TenantContext, *, campaign_id: str, name: str) -> dict[str, Any] | None:
        """Name the campaign's current state a save point: pinned, so retention keeps it (RQ-5.7)."""
        pinned = self.pin_current_state(context, campaign_id=campaign_id)
        if pinned is None:
            return None
        self.connection.execute(
            """
            UPDATE omnix_rpg_snapshots SET save_point_name = NULL
             WHERE workspace_id = %s AND campaign_id = %s AND save_point_name = %s AND id <> %s
            """,
            (context.workspace_id, campaign_id, name, pinned["id"]),
        )
        self.connection.execute(
            "UPDATE omnix_rpg_snapshots SET save_point_name = %s WHERE workspace_id = %s AND id = %s",
            (name, context.workspace_id, pinned["id"]),
        )
        return {"name": name, "revision": pinned["revision"]}

    def save_points(self, context: TenantContext, campaign_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT save_point_name, revision, created_at FROM omnix_rpg_snapshots
             WHERE workspace_id = %s AND campaign_id = %s AND save_point_name IS NOT NULL ORDER BY revision
            """,
            (context.workspace_id, campaign_id),
        ).fetchall()
        return [{"name": str(row[0]), "revision": int(row[1]), "created_at": row[2].isoformat()} for row in rows]

    def delete_save_point(self, context: TenantContext, *, campaign_id: str, name: str) -> bool:
        """Forget a save point: its snapshot loses its name and its pin (retention may then fold it away)."""
        cursor = self.connection.execute(
            """
            UPDATE omnix_rpg_snapshots SET save_point_name = NULL, pinned = false
             WHERE workspace_id = %s AND campaign_id = %s AND save_point_name = %s
            """,
            (context.workspace_id, campaign_id, name),
        )
        return cursor.rowcount == 1

    def pin_current_state(
        self,
        context: TenantContext,
        *,
        campaign_id: str,
        document_version: int | None = None,
    ) -> dict[str, Any] | None:
        """Pin the campaign's current state as the snapshot at its revision (the pre-upgrade backup, RQ-1.7).

        A snapshot already at that revision is pinned in place. None when the campaign does not exist.
        """
        campaign = self.get_campaign(context, campaign_id, for_update=True)
        if campaign is None:
            return None
        revision = campaign["revision"]
        if document_version is None:
            document_version = _document_version_of(campaign["state"])
        existing = self.connection.execute(
            """
            UPDATE omnix_rpg_snapshots
               SET pinned = true, document_version = COALESCE(document_version, %s)
             WHERE workspace_id = %s AND campaign_id = %s AND revision = %s
            RETURNING id
            """,
            (document_version, context.workspace_id, campaign_id, revision),
        ).fetchone()
        if existing is not None:
            return {"id": str(existing[0]), "campaign_id": campaign_id, "revision": revision, "created": False}
        snapshot = self.create_snapshot(
            context,
            campaign_id=campaign_id,
            snapshot_id=f"snapshot:{campaign_id}:{revision}",
            revision=revision,
            state=campaign["state"],
            state_hash_value=campaign["state_hash"],
            engine_version=campaign["engine_version"],
            schema_version=campaign["schema_version"],
            pinned=True,
            document_version=document_version,
        )
        return {"id": snapshot["id"], "campaign_id": campaign_id, "revision": revision, "created": True}


    def put_campaign_artifact(
        self,
        context: TenantContext,
        *,
        campaign_id: str,
        kind: str,
        document: dict[str, Any],
    ) -> str:
        """Keep what the campaign's creation produced and no turn reads, once (RQ-1.1); the content hash.

        Writing the same content again is a no-op; different content replaces the kind's document.
        """
        encoded = canonical_json(document)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        self.connection.execute(
            """
            INSERT INTO omnix_rpg_campaign_artifacts (workspace_id, campaign_id, kind, document_jsonb, content_hash)
            VALUES (%s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (workspace_id, campaign_id, kind) DO UPDATE
               SET document_jsonb = EXCLUDED.document_jsonb, content_hash = EXCLUDED.content_hash
             WHERE omnix_rpg_campaign_artifacts.content_hash <> EXCLUDED.content_hash
            """,
            (context.workspace_id, campaign_id, kind, encoded, digest),
        )
        return digest

    def touched_maps_hash(self, context: TenantContext, campaign_id: str) -> str | None:
        """The hash of the campaign's map-instance snapshots changed in this transaction, in id order (RQ-1.4).

        A map instance's update stamps ``updated_at`` with the transaction's start time, so those are the ones
        this turn moved anyone on; ``None`` when it touched no map.
        """
        rows = self.connection.execute(
            "SELECT map_instance_id, snapshot_jsonb FROM omnix_rpg_campaign_map_instances "
            "WHERE workspace_id = %s AND campaign_id = %s AND updated_at = CURRENT_TIMESTAMP "
            "ORDER BY map_instance_id",
            (context.workspace_id, campaign_id),
        ).fetchall()
        if not rows:
            return None
        return hashlib.sha256(canonical_json([[str(row[0]), dict(row[1])] for row in rows]).encode("utf-8")).hexdigest()

    TURN_NARRATIONS_KEPT = 64  # as many as the document kept (it pruned to 48-50)

    def put_turn_narrations(
        self,
        context: TenantContext,
        *,
        campaign_id: str,
        narrations: Mapping[str, Mapping[str, Any]],
        kind: str = "narration",
    ) -> int:
        """Keep each turn's narration outside the campaign document (RQ-1.4); the number written.

        A turn's narration with the same content is not rewritten; only the newest ``TURN_NARRATIONS_KEPT`` stay.
        """
        written = 0
        for turn_id, document in sorted(narrations.items()):
            encoded = canonical_json(dict(document))
            digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            cursor = self.connection.execute(
                """
                INSERT INTO omnix_rpg_turn_narrations (workspace_id, campaign_id, turn_id, kind, document_jsonb, content_hash)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (workspace_id, campaign_id, turn_id, kind) DO UPDATE
                   SET document_jsonb = EXCLUDED.document_jsonb, content_hash = EXCLUDED.content_hash,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE omnix_rpg_turn_narrations.content_hash <> EXCLUDED.content_hash
                """,
                (context.workspace_id, campaign_id, str(turn_id), kind, encoded, digest),
            )
            written += max(0, cursor.rowcount or 0)
        if written:
            self.connection.execute(
                """
                DELETE FROM omnix_rpg_turn_narrations
                 WHERE workspace_id = %s AND campaign_id = %s AND kind = %s
                   AND turn_id NOT IN (
                       SELECT turn_id FROM omnix_rpg_turn_narrations
                        WHERE workspace_id = %s AND campaign_id = %s AND kind = %s
                        ORDER BY updated_at DESC, turn_id DESC LIMIT %s)
                """,
                (context.workspace_id, campaign_id, kind, context.workspace_id, campaign_id, kind,
                 self.TURN_NARRATIONS_KEPT),
            )
        return written

    def turn_narrations(self, context: TenantContext, campaign_id: str, *, kind: str = "narration") -> list[tuple[str, dict[str, Any]]]:
        """The campaign's kept turn narrations, oldest first: (turn id, narration)."""
        rows = self.connection.execute(
            "SELECT turn_id, document_jsonb FROM omnix_rpg_turn_narrations "
            "WHERE workspace_id = %s AND campaign_id = %s AND kind = %s "
            "ORDER BY updated_at, turn_id LIMIT %s",
            (context.workspace_id, campaign_id, kind, self.TURN_NARRATIONS_KEPT),
        ).fetchall()
        return [(str(row[0]), dict(row[1])) for row in rows]

    def get_campaign_artifacts(self, context: TenantContext, campaign_id: str) -> dict[str, dict[str, Any]]:
        """The campaign's creation artifacts by kind."""
        rows = self.connection.execute(
            # A campaign has a handful of artifact kinds; the limit only bounds a corrupt table.
            "SELECT kind, document_jsonb FROM omnix_rpg_campaign_artifacts "
            "WHERE workspace_id = %s AND campaign_id = %s ORDER BY kind LIMIT 64",
            (context.workspace_id, campaign_id),
        ).fetchall()
        return {str(row[0]): dict(row[1]) for row in rows}
