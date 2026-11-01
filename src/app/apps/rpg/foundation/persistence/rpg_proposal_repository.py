"""The proposal record (evolution roadmap EV-11, migration 0187).

Work done off the turn is stored here as typed proposals, never written to the campaign. A turn reads the pending
proposals of earlier revisions when it loads, folds them in through their owning rules, and its commit settles each
one, folded or dropped, only while it is still pending: a proposal another turn settled first fails the commit
(``ProposalAlreadySettled``), which is the revision conflict two racing turns meet anyway.
"""
from __future__ import annotations

from typing import Any, Iterable

from app.persistence.errors import RevisionConflict
from app.persistence.tenant import TenantContext

from .rpg_repository import canonical_json

PENDING_READ_LIMIT = 200  # the most a turn folds in at once; the rest wait for the next


class ProposalAlreadySettled(RevisionConflict):
    """A proposal the turn folded in was settled by another turn first."""


def _proposal(row: Any) -> dict[str, Any]:
    return {"proposal_id": str(row[0]), "kind": str(row[1]), "source": str(row[2]), "after_revision": int(row[3]),
            "reason": str(row[4] or ""), "payload": dict(row[5] or {}), "status": str(row[6]),
            "settled_by_turn_id": row[7], "drop_reason": row[8]}


_COLUMNS = ("proposal_id, kind, source, after_revision, reason, payload_jsonb, status, settled_by_turn_id, "
            "drop_reason")


class PostgresRpgProposalRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def put(self, context: TenantContext, *, campaign_id: str, proposal_id: str, kind: str, source: str,
            after_revision: int, payload: dict[str, Any], reason: str = "") -> bool:
        """Store one proposal; False when a proposal with this id is already stored (a source's retry)."""
        row = self.connection.execute(
            """
            INSERT INTO omnix_rpg_proposals (workspace_id, campaign_id, proposal_id, kind, source, after_revision,
                                             reason, payload_jsonb)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (workspace_id, campaign_id, proposal_id) DO NOTHING
            RETURNING 1
            """,
            (context.workspace_id, campaign_id, proposal_id, kind, source, int(after_revision), reason[:2000],
             canonical_json(payload)),
        ).fetchone()
        return row is not None

    def drop_undone(self, context: TenantContext, *, campaign_id: str, after_revision: int, turn_id: str,
                    revision: int) -> int:
        """A rewind back to ``after_revision``: what was proposed after it belongs to the timeline undone, and is
        dropped (a name heard only there is not heard in the game restored). How many."""
        rows = self.connection.execute(
            """
            UPDATE omnix_rpg_proposals
               SET status = 'dropped', settled_by_turn_id = %s, settled_revision = %s, drop_reason = 'rewound'
             WHERE workspace_id = %s AND campaign_id = %s AND status = 'pending' AND after_revision > %s
            RETURNING proposal_id
            """,
            (turn_id, int(revision), context.workspace_id, campaign_id, int(after_revision)),
        ).fetchall()
        return len(rows)

    def pending(self, context: TenantContext, campaign_id: str, *, through_revision: int,
                limit: int = PENDING_READ_LIMIT) -> list[dict[str, Any]]:
        """The proposals still pending that came after a revision at or before ``through_revision``, in the order a
        turn folds them in: by that revision, then by id."""
        rows = self.connection.execute(
            f"""
            SELECT {_COLUMNS} FROM omnix_rpg_proposals
             WHERE workspace_id = %s AND campaign_id = %s AND status = 'pending' AND after_revision <= %s
             ORDER BY after_revision, proposal_id LIMIT %s
            """,
            (context.workspace_id, campaign_id, int(through_revision), max(1, int(limit))),
        ).fetchall()
        return [_proposal(row) for row in rows]

    def get(self, context: TenantContext, campaign_id: str, proposal_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {_COLUMNS} FROM omnix_rpg_proposals "
            "WHERE workspace_id = %s AND campaign_id = %s AND proposal_id = %s",
            (context.workspace_id, campaign_id, proposal_id),
        ).fetchone()
        return _proposal(row) if row is not None else None

    def settle(self, context: TenantContext, *, campaign_id: str, turn_id: str, revision: int,
               folded: Iterable[str], dropped: Iterable[tuple[str, str]]) -> None:
        """Mark what a committing turn folded in and what its rules dropped, each only while still pending; one that
        is not raises ``ProposalAlreadySettled`` and the commit rolls back."""
        settled = [(proposal_id, "folded", None) for proposal_id in folded]
        settled += [(proposal_id, "dropped", reason[:500]) for proposal_id, reason in dropped]
        for proposal_id, status, drop_reason in settled:
            row = self.connection.execute(
                """
                UPDATE omnix_rpg_proposals
                   SET status = %s, settled_by_turn_id = %s, settled_revision = %s, drop_reason = %s
                 WHERE workspace_id = %s AND campaign_id = %s AND proposal_id = %s AND status = 'pending'
                RETURNING 1
                """,
                (status, turn_id, int(revision), drop_reason, context.workspace_id, campaign_id, proposal_id),
            ).fetchone()
            if row is None:
                raise ProposalAlreadySettled(f"proposal {proposal_id} of campaign {campaign_id} is no longer pending")
