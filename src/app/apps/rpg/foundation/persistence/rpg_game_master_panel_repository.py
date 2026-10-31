"""The game master's panel log (evolution roadmap EV-0, migration 0188): questions and the answers shown."""
from __future__ import annotations

from typing import Any

from app.persistence.tenant import TenantContext

from .rpg_repository import canonical_json


class PostgresRpgGameMasterPanelRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def append(self, context: TenantContext, *, campaign_id: str, revision: int, question: str, answer: str,
               withheld: bool, wish: dict[str, Any] | None) -> int:
        row = self.connection.execute(
            """
            INSERT INTO omnix_rpg_game_master_panel (workspace_id, campaign_id, owner_user_id, revision, question,
                                                     answer, withheld, wish_jsonb)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb) RETURNING id
            """,
            (context.workspace_id, campaign_id, context.user_id or "", int(revision), question[:1000], answer[:4000],
             bool(withheld), canonical_json(wish) if wish else None),
        ).fetchone()
        return int(row[0])

    def recent(self, context: TenantContext, campaign_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id, revision, question, answer, withheld, wish_jsonb, created_at FROM omnix_rpg_game_master_panel
             WHERE workspace_id = %s AND campaign_id = %s ORDER BY id DESC LIMIT %s
            """,
            (context.workspace_id, campaign_id, max(1, min(200, int(limit)))),
        ).fetchall()
        return [{"id": int(row[0]), "revision": int(row[1]), "question": str(row[2]), "answer": str(row[3]),
                 "withheld": bool(row[4]), "wish": dict(row[5]) if row[5] else None, "asked_at": row[6].isoformat()}
                for row in rows]

    def asked_by_owner(self, context: TenantContext, *, window_seconds: int) -> int:
        row = self.connection.execute(
            """
            SELECT count(*) FROM omnix_rpg_game_master_panel
             WHERE workspace_id = %s AND owner_user_id = %s
               AND created_at > CURRENT_TIMESTAMP - make_interval(secs => %s)
            """,
            (context.workspace_id, context.user_id or "", int(window_seconds)),
        ).fetchone()
        return int(row[0] or 0)
