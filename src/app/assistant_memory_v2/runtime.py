from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.persistence.database import PostgresDatabase, default_database

from .authority import AuthorityEpochState, PostgresMemoryV2AuthorityStore
from .contracts import MemoryAuthorityEpoch, MemorySpaceKey, Observation, RetrievalQuery
from .episode_store import PostgresMemoryV2EpisodeStore
from .federated_retrieval import FederatedMemoryV2Retriever
from .grant_store import PostgresMemoryV2GrantStore
from .observation_store import (
    ObservationAppendRequest,
    ObservationIdempotencyConflict,
    ObservationStoreError,
    PostgresMemoryV2ObservationStore,
    _canonical_json,
    _observation_from_row,
    _space_values,
    observation_content_digest,
)
from .relationship_store import PostgresMemoryV2RelationshipStore
from .retrieval import UnifiedMemoryV2Retriever
from .search_index import PostgresMemoryV2SearchIndex


class MemoryV2RuntimeError(RuntimeError):
    pass


class MemoryV2NotAuthoritativeError(MemoryV2RuntimeError):
    pass


class AuthoritativeIngestSequenceError(MemoryV2RuntimeError):
    pass


class UnsafeMemoryRollbackError(MemoryV2RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MemoryV2SpaceOperationalStatus:
    receipt_id: str
    space: MemorySpaceKey
    cutover_authoritative_event_watermark: int
    cutover_observation_watermark: int
    current_authoritative_event_watermark: int
    current_observation_watermark: int
    graph_revision: int
    index_graph_revision: int
    index_stale: bool
    governance_changed: bool
    rollback_safe: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MemoryV2OperationalStatus:
    epoch: int
    authority: str
    previous_epoch: int | None
    activated_at: datetime
    activated_by: str
    legacy_read_only: bool
    v2_writes_allowed: bool
    rollback_safe: bool
    rollback_reasons: tuple[str, ...]
    spaces: tuple[MemoryV2SpaceOperationalStatus, ...]


_OBSERVATION_COLUMNS = """
observation_id, principal_id, owner_type, owner_id, authority_sequence,
idempotency_key, visibility_kind, visibility_scope_id, event_type, occurred_at,
provenance, recorded_at, payload, correlation_id, schema_version, content_digest
"""


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class PostgresMemoryV2Runtime:
    """Production authority boundary for canonical Memory v2 reads and writes.

    Low-level stores remain useful for replay, migration, and tests. Production callers use
    this facade so a write is impossible before the v2 authority epoch, authoritative-event
    and observation watermarks advance atomically, and rollback cannot silently discard
    post-cutover evidence or resurrect governed-away content.
    """

    def __init__(
        self,
        database: PostgresDatabase | None = None,
        *,
        authority_store: PostgresMemoryV2AuthorityStore | None = None,
    ) -> None:
        self.database = database or default_database()
        self.authority_store = authority_store or PostgresMemoryV2AuthorityStore(self.database)
        self.observation_store = self.authority_store.observation_store
        self.graph_store = self.authority_store.graph_store
        self.search_index = self.authority_store.search_index
        self.episode_store = PostgresMemoryV2EpisodeStore(self.database)
        self.relationship_store = PostgresMemoryV2RelationshipStore(self.database)
        self.grant_store = PostgresMemoryV2GrantStore(self.database)
        self.local_retriever = UnifiedMemoryV2Retriever(
            graph_store=self.graph_store,
            observation_store=self.observation_store,
            episode_store=self.episode_store,
            relationship_store=self.relationship_store,
            index_graph_revision_provider=self.search_index.index_graph_revision,
        )
        self.federated_retriever = FederatedMemoryV2Retriever(
            local_retriever=self.local_retriever,
            grant_store=self.grant_store,
        )

    def current(self) -> AuthorityEpochState:
        return self.authority_store.current()

    def assert_v2_authoritative(self) -> AuthorityEpochState:
        state = self.current()
        if state.epoch.authority != "v2":
            raise MemoryV2NotAuthoritativeError(
                "Memory v2 canonical access requires an active v2 authority epoch"
            )
        return state

    def retrieve(self, query: RetrievalQuery):
        self.assert_v2_authoritative()
        return self.federated_retriever.retrieve(query)

    @staticmethod
    def _lock_v2_authority(connection: Any) -> int:
        row = connection.execute(
            """
            SELECT c.current_epoch, e.authority
              FROM omnix_memory_v2_authority_current c
              JOIN omnix_memory_v2_authority_epochs e ON e.epoch = c.current_epoch
             WHERE c.singleton = TRUE
             FOR UPDATE OF c
            """
        ).fetchone()
        if row is None:
            raise MemoryV2RuntimeError("current memory authority epoch is missing")
        if str(row[1]) != "v2":
            raise MemoryV2NotAuthoritativeError(
                "Memory v2 canonical writes are disabled while v1 is authoritative"
            )
        return int(row[0])

    def append_authoritative(
        self,
        request: ObservationAppendRequest,
        *,
        authoritative_event_sequence: int,
    ) -> Observation:
        """Atomically append one authoritative event as one observation.

        The externally assigned event sequence must be the exact next per-space observation
        sequence. This prevents reordered or skipped event-feed delivery from being hidden by
        the Observation Store's local sequence allocator.
        """

        sequence = int(authoritative_event_sequence)
        if sequence < 1:
            raise AuthoritativeIngestSequenceError(
                "authoritative event sequence must be positive"
            )
        digest = observation_content_digest(request)
        values = _space_values(request.space)
        with self.database.transaction() as connection:
            self._lock_v2_authority(connection)
            last_sequence, observation_watermark = (
                PostgresMemoryV2ObservationStore._ensure_and_lock_stream(
                    connection,
                    request.space,
                )
            )
            event_row = connection.execute(
                """
                SELECT authoritative_event_watermark
                  FROM omnix_memory_v2_authority_streams
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                """,
                values,
            ).fetchone()
            if event_row is None:  # pragma: no cover - stream invariant
                raise ObservationStoreError("authoritative event stream is missing")
            event_watermark = int(event_row[0])

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
                if observation.authority_sequence != sequence:
                    raise AuthoritativeIngestSequenceError(
                        "idempotent observation belongs to a different authoritative sequence"
                    )
                if event_watermark < sequence:
                    raise AuthoritativeIngestSequenceError(
                        "authoritative event watermark trails an already committed observation"
                    )
                return observation

            expected_previous = sequence - 1
            if (
                last_sequence != expected_previous
                or observation_watermark != expected_previous
                or event_watermark != expected_previous
            ):
                raise AuthoritativeIngestSequenceError(
                    "authoritative event sequence is not the exact next synchronized sequence"
                )

            observation_id = request.observation_id or f"obs:{__import__('uuid').uuid4()}"
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
                    sequence,
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
            stream_row = connection.execute(
                """
                UPDATE omnix_memory_v2_authority_streams
                   SET last_sequence = %s,
                       observation_watermark = %s,
                       authoritative_event_watermark = %s,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                   AND last_sequence = %s
                   AND observation_watermark = %s
                   AND authoritative_event_watermark = %s
                RETURNING last_sequence
                """,
                (
                    sequence,
                    sequence,
                    sequence,
                    *values,
                    expected_previous,
                    expected_previous,
                    expected_previous,
                ),
            ).fetchone()
            if row is None or stream_row is None:  # pragma: no cover - locked invariant
                raise ObservationStoreError(
                    "authoritative observation append failed to advance synchronized watermarks"
                )
            return _observation_from_row(row)

    def operational_status(self) -> MemoryV2OperationalStatus:
        current = self.current()
        space_statuses: list[MemoryV2SpaceOperationalStatus] = []
        rollback_reasons: list[str] = []
        if current.epoch.authority != "v2":
            rollback_reasons.append("v2_not_authoritative")
        for receipt_id in current.readiness_receipt_ids:
            receipt = self.authority_store.get_readiness_receipt(receipt_id)
            if receipt is None:
                rollback_reasons.append(f"missing_cutover_receipt:{receipt_id}")
                continue
            marks = receipt.readiness.watermarks
            current_event = self.authority_store.authoritative_event_watermark(receipt.space)
            current_observation = self.observation_store.watermark(receipt.space)
            graph_state = self.graph_store.state(receipt.space)
            index_status = self.search_index.status(receipt.space)
            governance_changed = (
                index_status.governance_digest != receipt.index_governance_digest
            )
            reasons: list[str] = []
            if current_event != marks.authoritative_event:
                reasons.append("authoritative_event_advanced")
            if current_observation != marks.observation:
                reasons.append("observation_log_advanced")
            if governance_changed:
                reasons.append("governance_changed")
            rollback_safe = not reasons
            if not rollback_safe:
                rollback_reasons.extend(
                    f"{receipt.space.owner_type}:{receipt.space.owner_id}:{reason}"
                    for reason in reasons
                )
            space_statuses.append(
                MemoryV2SpaceOperationalStatus(
                    receipt_id=receipt_id,
                    space=receipt.space,
                    cutover_authoritative_event_watermark=marks.authoritative_event,
                    cutover_observation_watermark=marks.observation,
                    current_authoritative_event_watermark=current_event,
                    current_observation_watermark=current_observation,
                    graph_revision=graph_state.graph_revision,
                    index_graph_revision=index_status.state.index_graph_revision,
                    index_stale=index_status.stale,
                    governance_changed=governance_changed,
                    rollback_safe=rollback_safe,
                    reasons=tuple(reasons),
                )
            )
        return MemoryV2OperationalStatus(
            epoch=current.epoch.epoch,
            authority=current.epoch.authority,
            previous_epoch=current.epoch.previous_epoch,
            activated_at=current.epoch.activated_at,
            activated_by=current.epoch.activated_by,
            legacy_read_only=current.epoch.authority == "v2",
            v2_writes_allowed=current.epoch.authority == "v2",
            rollback_safe=(current.epoch.authority == "v2" and not rollback_reasons),
            rollback_reasons=tuple(rollback_reasons),
            spaces=tuple(space_statuses),
        )

    def rollback_to_v1(
        self,
        *,
        activated_by: str,
        reason: str,
    ) -> AuthorityEpochState:
        if not activated_by.strip():
            raise ValueError("activated_by is required")
        if not reason.strip():
            raise ValueError("rollback reason is required")

        with self.database.transaction() as connection:
            current_row = connection.execute(
                """
                SELECT e.epoch, e.authority, e.activated_at, e.previous_epoch,
                       e.readiness, e.readiness_receipt_ids, e.activated_by, e.reason
                  FROM omnix_memory_v2_authority_current c
                  JOIN omnix_memory_v2_authority_epochs e ON e.epoch = c.current_epoch
                 WHERE c.singleton = TRUE
                 FOR UPDATE OF c, e
                """
            ).fetchone()
            if current_row is None:  # pragma: no cover
                raise MemoryV2RuntimeError("current memory authority epoch is missing")
            current = PostgresMemoryV2AuthorityStore._epoch_from_row(current_row)
            if current.epoch.authority == "v1":
                return current

            for receipt_id in current.readiness_receipt_ids:
                receipt_row = connection.execute(
                    """
                    SELECT principal_id, owner_type, owner_id,
                           authoritative_event_watermark, observation_watermark,
                           index_governance_digest
                      FROM omnix_memory_v2_cutover_readiness_receipts
                     WHERE receipt_id = %s
                     FOR UPDATE
                    """,
                    (receipt_id,),
                ).fetchone()
                if receipt_row is None:
                    raise UnsafeMemoryRollbackError(
                        f"cutover receipt is missing: {receipt_id}"
                    )
                space = MemorySpaceKey(
                    principal_id=str(receipt_row[0]),
                    owner_type=str(receipt_row[1]),
                    owner_id=str(receipt_row[2]),
                )
                stream = connection.execute(
                    """
                    SELECT authoritative_event_watermark, observation_watermark
                      FROM omnix_memory_v2_authority_streams
                     WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                     FOR UPDATE
                    """,
                    _space_values(space),
                ).fetchone()
                if stream is None:
                    raise UnsafeMemoryRollbackError(
                        f"authority stream is missing for {space.owner_type}:{space.owner_id}"
                    )
                if (
                    int(stream[0]) != int(receipt_row[3])
                    or int(stream[1]) != int(receipt_row[4])
                ):
                    raise UnsafeMemoryRollbackError(
                        "rollback would discard post-cutover Memory v2 evidence"
                    )
                governance_digest = PostgresMemoryV2SearchIndex._governance_digest(
                    connection,
                    space,
                )
                if governance_digest != str(receipt_row[5]):
                    raise UnsafeMemoryRollbackError(
                        "rollback would resurrect memory changed by post-cutover governance"
                    )

            max_epoch_row = connection.execute(
                "SELECT COALESCE(MAX(epoch), 0) FROM omnix_memory_v2_authority_epochs"
            ).fetchone()
            next_epoch = int(max_epoch_row[0]) + 1
            activated_at = datetime.now(timezone.utc)
            epoch = MemoryAuthorityEpoch(
                epoch=next_epoch,
                authority="v1",
                activated_at=activated_at,
                previous_epoch=current.epoch.epoch,
                readiness=None,
                activated_by=activated_by,
            )
            connection.execute(
                """
                INSERT INTO omnix_memory_v2_authority_epochs (
                    epoch, authority, activated_at, previous_epoch, readiness,
                    readiness_receipt_ids, activated_by, reason
                ) VALUES (%s, 'v1', %s, %s, NULL, %s::jsonb, %s, %s)
                """,
                (
                    epoch.epoch,
                    epoch.activated_at,
                    epoch.previous_epoch,
                    _json(current.readiness_receipt_ids),
                    activated_by,
                    reason,
                ),
            )
            connection.execute(
                """
                UPDATE omnix_memory_v2_authority_current
                   SET current_epoch = %s, updated_at = CURRENT_TIMESTAMP
                 WHERE singleton = TRUE AND current_epoch = %s
                """,
                (next_epoch, current.epoch.epoch),
            )
        return AuthorityEpochState(
            epoch=epoch,
            readiness_receipt_ids=current.readiness_receipt_ids,
            reason=reason,
        )
