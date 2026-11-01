"""A campaign's spoken audio, by render identity (evolution roadmap EV-13, migration 0192)."""
from __future__ import annotations

from typing import Any

from app.persistence.tenant import TenantContext


class PostgresRpgSpeechAudioRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def get(self, context: TenantContext, campaign_id: str, render_key: str) -> tuple[bytes, str] | None:
        row = self.connection.execute(
            "SELECT audio, mime FROM omnix_rpg_speech_audio WHERE workspace_id = %s AND campaign_id = %s"
            " AND render_key = %s",
            (context.workspace_id, campaign_id, render_key),
        ).fetchone()
        return (bytes(row[0]), str(row[1])) if row else None

    def put(self, context: TenantContext, campaign_id: str, render_key: str, *, voice_id: str, audio: bytes,
            mime: str = "audio/wav") -> None:
        self.connection.execute(
            """
            INSERT INTO omnix_rpg_speech_audio (workspace_id, campaign_id, render_key, voice_id, mime, audio)
            VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (workspace_id, campaign_id, render_key) DO NOTHING
            """,
            (context.workspace_id, campaign_id, render_key, voice_id, mime, audio),
        )


__all__ = ["PostgresRpgSpeechAudioRepository"]
