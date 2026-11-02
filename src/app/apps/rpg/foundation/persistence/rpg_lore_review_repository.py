"""The world's lore review queue (evolution roadmap EV-0, part 2; migration 0189): the game master's drafts."""
from __future__ import annotations

from typing import Any

from app.persistence.tenant import TenantContext

from .rpg_repository import canonical_json

_COLUMNS = ("id, world_id, campaign_id, entry_id, family, name, group_key, entry_jsonb, provenance_jsonb, status, "
            "findings_jsonb, canon_id, linked_to, created_at, decided_at")


def _row(row: Any) -> dict[str, Any]:
    return {"id": int(row[0]), "world_id": str(row[1]), "campaign_id": str(row[2]), "entry_id": str(row[3]),
            "family": str(row[4]), "name": str(row[5]), "group_key": str(row[6]), "entry": dict(row[7] or {}),
            "provenance": dict(row[8] or {}), "status": str(row[9]), "findings": row[10],
            "canon_id": str(row[11] or ""), "linked_to": int(row[12]) if row[12] is not None else None,
            "created_at": row[13].isoformat(), "decided_at": row[14].isoformat() if row[14] else None}


class PostgresRpgLoreReviewRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def file(self, context: TenantContext, *, world_id: str, campaign_id: str, entry_id: str, family: str, name: str,
             group_key: str, entry: dict[str, Any], provenance: dict[str, Any]) -> int | None:
        """A draft filed once (by campaign and entry); None when it was filed already."""
        row = self.connection.execute(
            """
            INSERT INTO omnix_rpg_lore_review (workspace_id, world_id, campaign_id, entry_id, family, name, group_key,
                                               entry_jsonb, provenance_jsonb)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            ON CONFLICT (workspace_id, campaign_id, entry_id) DO NOTHING RETURNING id
            """,
            (context.workspace_id, world_id, campaign_id, entry_id, family, name[:120], group_key,
             canonical_json(entry), canonical_json(provenance)),
        ).fetchone()
        return int(row[0]) if row else None

    def queue(self, context: TenantContext, world_id: str, *, status: str = "") -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"SELECT {_COLUMNS} FROM omnix_rpg_lore_review WHERE workspace_id = %s AND world_id = %s"
            " AND (%s = '' OR status = %s) ORDER BY group_key, id LIMIT 5000",
            (context.workspace_id, world_id, status, status),
        ).fetchall()
        return [_row(row) for row in rows]

    def get(self, context: TenantContext, draft_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {_COLUMNS} FROM omnix_rpg_lore_review WHERE workspace_id = %s AND id = %s",
            (context.workspace_id, int(draft_id)),
        ).fetchone()
        return _row(row) if row else None

    def record_findings(self, context: TenantContext, draft_id: int, findings: dict[str, Any]) -> None:
        self.connection.execute(
            "UPDATE omnix_rpg_lore_review SET findings_jsonb = %s::jsonb WHERE workspace_id = %s AND id = %s",
            (canonical_json(findings), context.workspace_id, int(draft_id)),
        )

    def decide(self, context: TenantContext, draft_id: int, *, status: str, entry: dict[str, Any] | None = None,
               canon_id: str = "", linked_to: int | None = None) -> bool:
        """The author's decision on a pending draft (False when it was decided already)."""
        row = self.connection.execute(
            """
            UPDATE omnix_rpg_lore_review
               SET status = %s, entry_jsonb = COALESCE(%s::jsonb, entry_jsonb), canon_id = %s, linked_to = %s,
                   decided_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND id = %s AND status = 'pending' RETURNING id
            """,
            (status, canonical_json(entry) if entry is not None else None, canon_id, linked_to,
             context.workspace_id, int(draft_id)),
        ).fetchone()
        return row is not None


    def reopen(self, context: TenantContext, draft_id: int) -> bool:
        """An approval withdrawn: the draft waits for a decision again."""
        row = self.connection.execute(
            """
            UPDATE omnix_rpg_lore_review SET status = 'pending', canon_id = '', decided_at = NULL
             WHERE workspace_id = %s AND id = %s AND status = 'approved' RETURNING id
            """,
            (context.workspace_id, int(draft_id)),
        ).fetchone()
        return row is not None


__all__ = ["PostgresRpgLoreReviewRepository"]
