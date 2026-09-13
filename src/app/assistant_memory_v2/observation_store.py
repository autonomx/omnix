from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.persistence.database import PostgresDatabase, default_database

from .contracts import (
    MemorySpaceKey,
    Observation,
    ObservationDisposition,
    ObservationProvenance,
    VisibilityScope,
)


class ObservationStoreError(RuntimeError):
    pass


class ObservationIdempotencyConflict(ObservationStoreError):
    pass


class ObservationNotFound(ObservationStoreError):
    pass


@dataclass(frozen=True, slots=True)
class ObservationAppendRequest:
    space: MemorySpaceKey
    visibility_scope: VisibilityScope
    event_type: str
    occurred_at: datetime
    provenance: ObservationProvenance
    idempotency_key: str
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    schema_version: str = "memory-v2-observation@1"
    observation_id: str | None = None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def observation_content_digest(request: ObservationAppendRequest) -> str:
    material = {
        "space": request.space.model_dump(mode="json"),
        "visibility_scope": request.visibility_scope.model_dump(mode="json"),
        "event_type": request.event_type,
        "occurred_at": request.occurred_at.astimezone(timezone.utc).isoformat(),
        "payload": request.payload,
        "provenance": request.provenance.model_dump(mode="json"),
        "correlation_id": request.correlation_id,
        "schema_version": request.schema_version,
    }
    return hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()


def _space_values(space: MemorySpaceKey) -> tuple[str, str, str]:
    return space.principal_id, space.owner_type, space.owner_id


def _observation_from_row(row: Any) -> Observation:
    provenance = dict(row[10])
    return Observation(
        observation_id=str(row[0]),
        authority_sequence=int(row[4]),
        idempotency_key=str(row[5]),
        space=MemorySpaceKey(
            principal_id=str(row[1]),
            owner_type=str(row[2]),
            owner_id=str(row[3]),
        ),
        visibility_scope=VisibilityScope(kind=str(row[6]), scope_id=str(row[7])),
        event_type=str(row[8]),
        occurred_at=row[9],
        recorded_at=row[11],
        payload=dict(row[12]),
        provenance=ObservationProvenance(**provenance),
        correlation_id=str(row[13]) if row[13] is not None else None,
        schema_version=str(row[14]),
        content_digest=str(row[15]),
    )


_OBSERVATION_COLUMN_NAMES = (
    "observation_id",
    "principal_id",
    "owner_type",
    "owner_id",
    "authority_sequence",
    "idempotency_key",
    "visibility_kind",
    "visibility_scope_id",
    "event_type",
    "occurred_at",
    "provenance",
    "recorded_at",
    "payload",
    "correlation_id",
    "schema_version",
    "content_digest",
)
_OBSERVATION_COLUMNS = ", ".join(_OBSERVATION_COLUMN_NAMES)


def _qualified_observation_columns(alias: str) -> str:
    return ", ".join(f"{alias}.{name}" for name in _OBSERVATION_COLUMN_NAMES)


class PostgresMemoryV2ObservationStore:
    """Authoritative append-only evidence store for Memory v2.

    Sequence allocation is intentionally database serialized. No process-local lock or
    counter participates in authority allocation.
    """

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()

    @staticmethod
    def _ensure_and_lock_stream(connection: Any, space: MemorySpaceKey) -> tuple[int, int]:
        values = _space_values(space)
        connection.execute(
            """
            INSERT INTO omnix_memory_v2_authority_streams (
                principal_id, owner_type, owner_id, last_sequence, observation_watermark
            ) VALUES (%s, %s, %s, 0, 0)
            ON CONFLICT (principal_id, owner_type, owner_id) DO NOTHING
            """,
            values,
        )
        row = connection.execute(
            """
            SELECT last_sequence, observation_watermark
              FROM omnix_memory_v2_authority_streams
             WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
             FOR UPDATE
            """,
            values,
        ).fetchone()
        if row is None:  # pragma: no cover - defensive database invariant
            raise ObservationStoreError("failed to establish Memory v2 authority stream")
        return int(row[0]), int(row[1])

    def append(self, request: ObservationAppendRequest) -> Observation:
        digest = observation_content_digest(request)
        values = _space_values(request.space)
        with self.database.transaction() as connection:
            last_sequence, watermark = self._ensure_and_lock_stream(connection, request.space)
            existing = connection.execute(
                f"""
                SELECT {_OBSERVATION_COLUMNS}
                  FROM omnix_memory_v2_observations
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                   AND idempotency_key = %s
                """,
                (*values, request.idempotency_key),
            ).fetchone()
            if existing is not None:
                observation = _observation_from_row(existing)
                if observation.content_digest != digest:
                    raise ObservationIdempotencyConflict(
                        "idempotency key already committed with different observation content"
                    )
                return observation

            next_sequence = last_sequence + 1
            observation_id = request.observation_id or f"obs:{uuid4()}"
            recorded_at = datetime.now(timezone.utc)
            provenance_json = _canonical_json(request.provenance.model_dump(mode="json"))
            payload_json = _canonical_json(request.payload)
            row = connection.execute(
                f"""
                INSERT INTO omnix_memory_v2_observations (
                    observation_id, principal_id, owner_type, owner_id,
                    authority_sequence, idempotency_key, visibility_kind,
                    visibility_scope_id, event_type, occurred_at, recorded_at,
                    payload, provenance, correlation_id, schema_version, content_digest
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s, %s, %s
                )
                RETURNING {_OBSERVATION_COLUMNS}
                """,
                (
                    observation_id,
                    *values,
                    next_sequence,
                    request.idempotency_key,
                    request.visibility_scope.kind,
                    request.visibility_scope.scope_id,
                    request.event_type,
                    request.occurred_at,
                    recorded_at,
                    payload_json,
                    provenance_json,
                    request.correlation_id,
                    request.schema_version,
                    digest,
                ),
            ).fetchone()
            connection.execute(
                """
                UPDATE omnix_memory_v2_authority_streams
                   SET last_sequence = %s,
                       observation_watermark = %s,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                   AND last_sequence = %s AND observation_watermark = %s
                """,
                (next_sequence, next_sequence, *values, last_sequence, watermark),
            )
            if row is None:  # pragma: no cover - INSERT RETURNING invariant
                raise ObservationStoreError("observation insert returned no row")
            return _observation_from_row(row)

    def get(self, space: MemorySpaceKey, observation_id: str) -> Observation | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                f"""
                SELECT {_OBSERVATION_COLUMNS}
                  FROM omnix_memory_v2_observations
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                   AND observation_id = %s
                """,
                (*_space_values(space), observation_id),
            ).fetchone()
        return _observation_from_row(row) if row is not None else None

    def list(
        self,
        space: MemorySpaceKey,
        *,
        after_sequence: int = 0,
        through_sequence: int | None = None,
        visible_scopes: Iterable[VisibilityScope] | None = None,
        include_inactive: bool = False,
        limit: int = 1000,
    ) -> list[Observation]:
        conditions = [
            "o.principal_id = %s",
            "o.owner_type = %s",
            "o.owner_id = %s",
            "o.authority_sequence > %s",
        ]
        params: list[Any] = [*_space_values(space), max(0, int(after_sequence))]
        if through_sequence is not None:
            conditions.append("o.authority_sequence <= %s")
            params.append(int(through_sequence))
        scopes = tuple(visible_scopes or ())
        if scopes:
            scope_terms: list[str] = []
            for scope in scopes:
                scope_terms.append("(o.visibility_kind = %s AND o.visibility_scope_id = %s)")
                params.extend((scope.kind, scope.scope_id))
            conditions.append("(" + " OR ".join(scope_terms) + ")")
        if not include_inactive:
            conditions.append("COALESCE(d.state, 'active') = 'active'")
        params.append(max(1, min(int(limit), 100_000)))
        columns = _qualified_observation_columns("o")
        with self.database.transaction() as connection:
            rows = connection.execute(
                f"""
                SELECT {columns}
                  FROM omnix_memory_v2_observations o
                  LEFT JOIN omnix_memory_v2_observation_dispositions d
                    ON d.observation_id = o.observation_id
                 WHERE {' AND '.join(conditions)}
                 ORDER BY o.authority_sequence ASC
                 LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        return [_observation_from_row(row) for row in rows]

    def watermark(self, space: MemorySpaceKey) -> int:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT observation_watermark
                  FROM omnix_memory_v2_authority_streams
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                """,
                _space_values(space),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def set_disposition(
        self,
        space: MemorySpaceKey,
        observation_id: str,
        *,
        state: str,
        actor_id: str,
        reason: str | None = None,
        changed_at: datetime | None = None,
    ) -> ObservationDisposition:
        if state not in {"active", "revoked", "purged"}:
            raise ValueError(f"unsupported observation disposition: {state}")
        timestamp = changed_at or datetime.now(timezone.utc)
        values = _space_values(space)
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT authority_sequence
                  FROM omnix_memory_v2_observations
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                   AND observation_id = %s
                 FOR UPDATE
                """,
                (*values, observation_id),
            ).fetchone()
            if row is None:
                raise ObservationNotFound(observation_id)
            sequence = int(row[0])
            connection.execute(
                """
                INSERT INTO omnix_memory_v2_observation_dispositions (
                    observation_id, principal_id, owner_type, owner_id,
                    authority_sequence, state, changed_at, reason, actor_id, revision
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                ON CONFLICT (observation_id) DO UPDATE
                   SET state = EXCLUDED.state,
                       changed_at = EXCLUDED.changed_at,
                       reason = EXCLUDED.reason,
                       actor_id = EXCLUDED.actor_id,
                       revision = omnix_memory_v2_observation_dispositions.revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                """,
                (observation_id, *values, sequence, state, timestamp, reason, actor_id),
            )
            if state == "purged":
                connection.execute(
                    """
                    UPDATE omnix_memory_v2_observations
                       SET payload = '{\"purged\":true}'::jsonb
                     WHERE observation_id = %s
                    """,
                    (observation_id,),
                )
        return ObservationDisposition(
            observation_id=observation_id,
            state=state,
            authority_sequence=sequence,
            changed_at=timestamp,
            reason=reason,
            actor_id=actor_id,
        )

    def disposition(self, observation_id: str) -> ObservationDisposition | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT observation_id, state, authority_sequence, changed_at, reason, actor_id
                  FROM omnix_memory_v2_observation_dispositions
                 WHERE observation_id = %s
                """,
                (observation_id,),
            ).fetchone()
        if row is None:
            return None
        return ObservationDisposition(
            observation_id=str(row[0]),
            state=str(row[1]),
            authority_sequence=int(row[2]),
            changed_at=row[3],
            reason=str(row[4]) if row[4] is not None else None,
            actor_id=str(row[5]),
        )
