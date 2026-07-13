from __future__ import annotations

from typing import Any

from app.characters.models import (
    CharacterProfile,
    CharacterProfileVersion,
    ConversationSegment,
    CreateCharacterRequest,
    InteractionMode,
    SharedMemoryAccess,
    TranscriptPolicy,
    UpdateCharacterRequest,
)
from app.characters.repository import CharacterConflictError, CharacterNotFoundError

from .database import PostgresDatabase, default_database
from .errors import EntityNotFound, RevisionConflict
from .identity_service import bootstrap_local_tenant
from .runtime import ensure_postgresql_runtime_ready
from .unit_of_work import unit_of_work


class PostgresCharacterRepositoryAdapter:
    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()
        ensure_postgresql_runtime_ready(self.database)
        self.context = bootstrap_local_tenant(self.database)

    def create(self, request: CreateCharacterRequest) -> CharacterProfile:
        character_id = self._normalize_id(request.id or request.display_name)
        try:
            with unit_of_work(self.database) as work:
                record = work.characters.create(
                    self.context,
                    character_id=character_id,
                    profile=self._request_profile(request),
                    visibility="private",
                    enabled=request.enabled,
                )
                work.commit()
        except Exception as exc:
            if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                raise CharacterConflictError(f"character already exists: {character_id}") from exc
            raise
        return self._profile(record)

    def get(self, character_id: str, *, include_archived: bool = False) -> CharacterProfile | None:
        with unit_of_work(self.database) as work:
            record = work.characters.get_character(
                self.context,
                character_id,
                include_archived=include_archived,
            )
            work.rollback()
        return self._profile(record) if record is not None else None

    def list(self, *, include_archived: bool = False) -> list[CharacterProfile]:
        with unit_of_work(self.database) as work:
            records = work.characters.list_characters(
                self.context,
                include_archived=include_archived,
                limit=500,
            )
            work.rollback()
        return [self._profile(record) for record in records]

    def update(self, character_id: str, request: UpdateCharacterRequest) -> CharacterProfile:
        current = self.get(character_id)
        if current is None:
            raise CharacterNotFoundError(character_id)
        payload = current.model_dump(mode="python")
        changes = request.model_dump(exclude={"expected_version"}, exclude_none=True)
        if changes.pop("clear_default_voice", False):
            changes["default_voice_asset_id"] = None
        profile = {
            "display_name": changes.get("display_name", current.display_name),
            "description": changes.get("description", current.description),
            "personality_prompt": changes.get(
                "personality_prompt", current.personality_prompt
            ),
            "default_greeting": changes.get("default_greeting", current.default_greeting),
            "default_voice_asset_id": changes.get(
                "default_voice_asset_id", current.default_voice_asset_id
            ),
            "speech_style": changes.get("speech_style", dict(current.speech_style)),
            "identity_policy": changes.get("identity_policy", dict(current.identity_policy)),
            "shared_memory_policy": changes.get(
                "shared_memory_policy", dict(current.shared_memory_policy)
            ),
        }
        try:
            with unit_of_work(self.database) as work:
                record = work.characters.update(
                    self.context,
                    character_id=character_id,
                    profile=profile,
                    expected_version=request.expected_version,
                )
                work.commit()
        except EntityNotFound as exc:
            raise CharacterNotFoundError(character_id) from exc
        except RevisionConflict as exc:
            raise CharacterConflictError(str(exc)) from exc
        return self._profile(record)

    def archive(self, character_id: str) -> CharacterProfile:
        current = self.get(character_id, include_archived=True)
        if current is None:
            raise CharacterNotFoundError(character_id)
        try:
            with unit_of_work(self.database) as work:
                record = work.characters.archive(
                    self.context,
                    character_id=character_id,
                    expected_revision=current.active_version,
                )
                work.commit()
        except RevisionConflict as exc:
            raise CharacterConflictError(str(exc)) from exc
        return self._profile(record)

    def versions(self, character_id: str) -> list[CharacterProfileVersion]:
        try:
            with unit_of_work(self.database) as work:
                records = work.characters.versions(self.context, character_id)
                work.rollback()
        except EntityNotFound as exc:
            raise CharacterNotFoundError(character_id) from exc
        return [
            CharacterProfileVersion(
                character_id=record["character_id"],
                version=record["version"],
                **record["profile"],
                created_at=record["created_at"],
            )
            for record in records
        ]

    def create_segment(
        self,
        *,
        session_id: str,
        interaction_mode: InteractionMode,
        character_id: str | None,
        profile_version: int | None,
        transcript_policy: TranscriptPolicy,
        read_memory: bool,
        write_memory: bool,
        shared_memory_access: SharedMemoryAccess,
        carryover_summary: str | None = None,
    ) -> ConversationSegment:
        import uuid

        if interaction_mode == "character" and not character_id:
            raise ValueError("character segment requires character_id")
        if interaction_mode == "system" and character_id:
            raise ValueError("system segment cannot have character_id")
        segment_id = f"segment:{uuid.uuid4().hex}"
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                INSERT INTO omnix_conversation_segments (
                    id, workspace_id, session_id, interaction_mode, character_id,
                    character_version, transcript_policy, read_memory, write_memory,
                    shared_memory_access, carryover_summary
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, session_id, interaction_mode, character_id,
                          character_version, transcript_policy, read_memory,
                          write_memory, shared_memory_access, carryover_summary,
                          started_at, ended_at
                """,
                (
                    segment_id,
                    self.context.workspace_id,
                    session_id,
                    interaction_mode,
                    character_id,
                    profile_version,
                    transcript_policy,
                    read_memory,
                    write_memory,
                    shared_memory_access,
                    carryover_summary,
                ),
            ).fetchone()
        return self._segment(row)

    def close_segment(self, segment_id: str) -> ConversationSegment | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                UPDATE omnix_conversation_segments
                   SET ended_at = COALESCE(ended_at, CURRENT_TIMESTAMP)
                 WHERE id = %s AND workspace_id = %s
                RETURNING id, session_id, interaction_mode, character_id,
                          character_version, transcript_policy, read_memory,
                          write_memory, shared_memory_access, carryover_summary,
                          started_at, ended_at
                """,
                (segment_id, self.context.workspace_id),
            ).fetchone()
        return self._segment(row) if row is not None else None

    def segments(self, session_id: str) -> list[ConversationSegment]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, interaction_mode, character_id,
                       character_version, transcript_policy, read_memory,
                       write_memory, shared_memory_access, carryover_summary,
                       started_at, ended_at
                  FROM omnix_conversation_segments
                 WHERE workspace_id = %s AND session_id = %s
                 ORDER BY started_at ASC, id ASC
                """,
                (self.context.workspace_id, session_id),
            ).fetchall()
        return [self._segment(row) for row in rows]

    @staticmethod
    def _normalize_id(value: str) -> str:
        import re

        normalized = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
        if not normalized:
            raise ValueError("character id is required")
        return normalized

    @staticmethod
    def _request_profile(request: CreateCharacterRequest) -> dict[str, Any]:
        return {
            "display_name": request.display_name.strip(),
            "description": request.description.strip(),
            "personality_prompt": request.personality_prompt.strip(),
            "default_greeting": request.default_greeting.strip(),
            "default_voice_asset_id": request.default_voice_asset_id,
            "speech_style": dict(request.speech_style),
            "identity_policy": dict(request.identity_policy),
            "shared_memory_policy": dict(request.shared_memory_policy),
        }

    @staticmethod
    def _profile(record: dict[str, Any]) -> CharacterProfile:
        return CharacterProfile(
            id=record["id"],
            **record["profile"],
            active_version=record["active_version"],
            enabled=record["enabled"],
            status=record["status"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
        )

    @staticmethod
    def _segment(row: Any) -> ConversationSegment:
        return ConversationSegment(
            id=str(row[0]),
            session_id=str(row[1]),
            interaction_mode=str(row[2]),
            character_id=str(row[3]) if row[3] is not None else None,
            profile_version=int(row[4]) if row[4] is not None else None,
            transcript_policy=str(row[5]),
            read_memory=bool(row[6]),
            write_memory=bool(row[7]),
            shared_memory_access=str(row[8]),
            carryover_summary=str(row[9]) if row[9] is not None else None,
            started_at=row[10].isoformat(),
            ended_at=row[11].isoformat() if row[11] is not None else None,
        )
