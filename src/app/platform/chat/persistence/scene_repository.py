"""A character chat's scene guests in PostgreSQL (``omnix_chat_scene_members``, owned by chat; companion 5.1)."""
from __future__ import annotations

from dataclasses import dataclass

from app.conversation.scene import MAX_SCENE_GUESTS
from app.persistence.database import PostgresDatabase, default_database
from app.security.tenant_context import RequestTenant


class SceneFullError(ValueError):
    """The chat already has its four guests."""


@dataclass(frozen=True)
class SceneSeat:
    character_id: str
    seat: int
    joined_at: str


class PostgresSceneMemberRepository:
    context = RequestTenant()

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()
        self.context = None  # follows the request tenant

    def guests(self, session_id: str) -> list[SceneSeat]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT character_id, seat, joined_at FROM omnix_chat_scene_members
                    WHERE workspace_id = %s AND session_id = %s ORDER BY seat LIMIT %s""",
                (self.context.workspace_id, session_id, MAX_SCENE_GUESTS),
            ).fetchall()
        return [_seat(row) for row in rows]

    def add_guest(self, session_id: str, character_id: str) -> SceneSeat:
        """Seat ``character_id`` in the first free seat; an existing guest keeps its seat."""
        with self.database.transaction() as connection:
            # The chat's row serialises two adds racing for the last seat.
            locked = connection.execute(
                "SELECT id FROM omnix_chat_sessions WHERE id = %s AND workspace_id = %s FOR UPDATE",
                (session_id, self.context.workspace_id),
            ).fetchone()
            if locked is None:
                raise LookupError("chat session not found")
            rows = connection.execute(
                """SELECT character_id, seat, joined_at FROM omnix_chat_scene_members
                    WHERE workspace_id = %s AND session_id = %s ORDER BY seat LIMIT %s""",
                (self.context.workspace_id, session_id, MAX_SCENE_GUESTS),
            ).fetchall()
            seats = [_seat(row) for row in rows]
            existing = next((seat for seat in seats if seat.character_id == character_id), None)
            if existing is not None:
                return existing
            free = [number for number in range(1, MAX_SCENE_GUESTS + 1) if number not in {seat.seat for seat in seats}]
            if not free:
                raise SceneFullError(f"a call has at most {MAX_SCENE_GUESTS} guests")
            row = connection.execute(
                """INSERT INTO omnix_chat_scene_members (workspace_id, session_id, character_id, seat)
                   VALUES (%s, %s, %s, %s) RETURNING character_id, seat, joined_at""",
                (self.context.workspace_id, session_id, character_id, free[0]),
            ).fetchone()
        return _seat(row)

    def remove_guest(self, session_id: str, character_id: str) -> bool:
        with self.database.transaction() as connection:
            row = connection.execute(
                """DELETE FROM omnix_chat_scene_members
                    WHERE workspace_id = %s AND session_id = %s AND character_id = %s RETURNING seat""",
                (self.context.workspace_id, session_id, character_id),
            ).fetchone()
        return row is not None

    def clear(self, session_id: str) -> int:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM omnix_chat_scene_members WHERE workspace_id = %s AND session_id = %s",
                (self.context.workspace_id, session_id),
            )
            return int(cursor.rowcount or 0)


def _seat(row) -> SceneSeat:
    return SceneSeat(character_id=str(row[0]), seat=int(row[1]), joined_at=row[2].isoformat())


def scene_members() -> PostgresSceneMemberRepository | None:
    """The scene repository of this runtime. Scenes need PostgreSQL: without it a call has no guests."""
    from app.persistence.runtime import uses_postgresql_runtime

    return PostgresSceneMemberRepository() if uses_postgresql_runtime() else None


__all__ = ["PostgresSceneMemberRepository", "SceneFullError", "SceneSeat", "scene_members"]
