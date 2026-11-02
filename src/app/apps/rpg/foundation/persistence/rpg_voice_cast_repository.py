"""A campaign's voice cast (evolution roadmap EV-13, migration 0190): who speaks in which voice."""
from __future__ import annotations

from typing import Any

from app.persistence.tenant import TenantContext


class PostgresRpgVoiceCastRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def cast(self, context: TenantContext, campaign_id: str) -> dict[str, dict[str, str]]:
        rows = self.connection.execute(
            "SELECT speaker_id, voice_id, voice_revision, chosen_by FROM omnix_rpg_voice_cast"
            " WHERE workspace_id = %s AND campaign_id = %s LIMIT 5000",
            (context.workspace_id, campaign_id),
        ).fetchall()
        return {str(row[0]): {"voice_id": str(row[1]), "voice_revision": str(row[2]), "chosen_by": str(row[3])}
                for row in rows}

    def put(self, context: TenantContext, campaign_id: str, speaker_id: str, *, voice_id: str, voice_revision: str,
            chosen_by: str, replace: bool = False) -> None:
        """A speaker's voice. A choice replaces one of its rank or below (the player's over the author's over an
        automatic cast), unless ``replace`` (the stored voice is no longer castable, or has changed)."""
        self.connection.execute(
            """
            INSERT INTO omnix_rpg_voice_cast (workspace_id, campaign_id, speaker_id, voice_id, voice_revision, chosen_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (workspace_id, campaign_id, speaker_id) DO UPDATE
               SET voice_id = EXCLUDED.voice_id, voice_revision = EXCLUDED.voice_revision,
                   chosen_by = EXCLUDED.chosen_by, updated_at = CURRENT_TIMESTAMP
             WHERE %s OR (CASE EXCLUDED.chosen_by WHEN 'player' THEN 3 WHEN 'author' THEN 2 ELSE 1 END)
                   >= (CASE omnix_rpg_voice_cast.chosen_by WHEN 'player' THEN 3 WHEN 'author' THEN 2 ELSE 1 END)
            """,
            (context.workspace_id, campaign_id, speaker_id, voice_id, voice_revision, chosen_by, bool(replace)),
        )


__all__ = ["PostgresRpgVoiceCastRepository"]
