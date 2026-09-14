from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.persistence.database import PostgresDatabase, default_database

from .consolidation import PostgresMemoryV2Consolidator
from .contracts import (
    CutoverReadiness,
    MemoryAuthorityEpoch,
    MemorySpaceKey,
    MemoryWatermarks,
)
from .derived_state import PostgresMemoryV2DerivedStateStore
from .graph_store import GraphReplayReport, PostgresMemoryV2GraphStore
from .legacy_shadow import PostgresMemoryV2ShadowEvaluationStore
from .observation_store import PostgresMemoryV2ObservationStore
from .replay import PostgresMemoryV2DerivedReplayValidator
from .search_index import PostgresMemoryV2SearchIndex


class MemoryAuthorityError(RuntimeError):
    pass


class CutoverNotReadyError(MemoryAuthorityError):
    pass


class StaleCutoverReceiptError(MemoryAuthorityError):
    pass


@dataclass(frozen=True, slots=True)
class SpaceCutoverReadinessReceipt:
    receipt_id: str
    space: MemorySpaceKey
    readiness: CutoverReadiness
    graph_source_observation_watermark: int
    index_source_observation_watermark: int
    index_governance_digest: str
    graph_validation_digest: str | None
    shadow_evaluation_id: str | None
    created_at: datetime
    governance_revision: int = 0
    derived_revision: int = 0
    derived_source_observation_watermark: int = 0
    derived_source_governance_revision: int = 0
    index_derived_revision: int = 0


@dataclass(frozen=True, slots=True)
class AuthorityEpochState:
    epoch: MemoryAuthorityEpoch
    readiness_receipt_ids: tuple[str, ...]
    reason: str | None = None


def _space_values(space: MemorySpaceKey) -> tuple[str, str, str]:
    return space.principal_id, space.owner_type, space.owner_id


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _readiness_receipt_from_row(row: Any) -> SpaceCutoverReadinessReceipt:
    space = MemorySpaceKey(
        principal_id=str(row[1]),
        owner_type=str(row[2]),
        owner_id=str(row[3]),
    )
    readiness = CutoverReadiness(
        watermarks=MemoryWatermarks(
            authoritative_event=int(row[4]),
            observation=int(row[5]),
            consolidation=int(row[6]),
            graph_revision=int(row[7]),
            index_graph_revision=int(row[9]),
            governance_revision=int(row[18]),
            derived_revision=int(row[19]),
            derived_observation_watermark=int(row[20]),
            index_derived_revision=int(row[22]),
        ),
        graph_validation_passed=bool(row[12]),
        shadow_quality_passed=bool(row[15]),
        indexes_caught_up=bool(row[16]),
        ready=bool(row[17]),
    )
    return SpaceCutoverReadinessReceipt(
        receipt_id=str(row[0]),
        space=space,
        readiness=readiness,
        graph_source_observation_watermark=int(row[8]),
        index_source_observation_watermark=int(row[10]),
        index_governance_digest=str(row[11]),
        graph_validation_digest=str(row[13]) if row[13] is not None else None,
        shadow_evaluation_id=str(row[14]) if row[14] is not None else None,
        created_at=row[23],
        governance_revision=int(row[18]),
        derived_revision=int(row[19]),
        derived_source_observation_watermark=int(row[20]),
        derived_source_governance_revision=int(row[21]),
        index_derived_revision=int(row[22]),
    )


_READINESS_COLUMNS = """
receipt_id, principal_id, owner_type, owner_id,
authoritative_event_watermark, observation_watermark, consolidation_watermark,
graph_revision, graph_source_observation_watermark,
index_graph_revision, index_source_observation_watermark, index_governance_digest,
graph_validation_passed, graph_validation_digest, shadow_evaluation_id,
shadow_quality_passed, indexes_caught_up, ready,
governance_revision, derived_revision, derived_source_observation_watermark,
derived_source_governance_revision, index_derived_revision, created_at
"""


class PostgresMemoryV2AuthorityStore:
    """Transactional v1 -> v2 authority cutover coordinator.

    Readiness is a receipt over exact evidence, derived-memory, governance, search, replay,
    and shadow-quality versions. Activation re-locks/revalidates those versions so a stale
    passing receipt cannot authorize cutover.
    """

    def __init__(
        self,
        database: PostgresDatabase | None = None,
        *,
        observation_store: PostgresMemoryV2ObservationStore | None = None,
        consolidator: PostgresMemoryV2Consolidator | None = None,
        graph_store: PostgresMemoryV2GraphStore | None = None,
        search_index: PostgresMemoryV2SearchIndex | None = None,
        shadow_store: PostgresMemoryV2ShadowEvaluationStore | None = None,
        derived_store: PostgresMemoryV2DerivedStateStore | None = None,
        derived_replay_validator: PostgresMemoryV2DerivedReplayValidator | None = None,
    ) -> None:
        self.database = database or default_database()
        self.observation_store = observation_store or PostgresMemoryV2ObservationStore(self.database)
        self.graph_store = graph_store or PostgresMemoryV2GraphStore(self.database)
        self.consolidator = consolidator or PostgresMemoryV2Consolidator(
            self.database,
            graph_store=self.graph_store,
            observation_store=self.observation_store,
        )
        self.search_index = search_index or PostgresMemoryV2SearchIndex(self.database)
        self.shadow_store = shadow_store or PostgresMemoryV2ShadowEvaluationStore(
            self.database,
            graph_store=self.graph_store,
            observation_store=self.observation_store,
        )
        self.derived_store = derived_store or PostgresMemoryV2DerivedStateStore(self.database)
        self.derived_replay_validator = (
            derived_replay_validator
            or PostgresMemoryV2DerivedReplayValidator(self.database)
        )

    def advance_authoritative_event_watermark(
        self,
        space: MemorySpaceKey,
        watermark: int,
    ) -> int:
        watermark = int(watermark)
        if watermark < 0:
            raise ValueError("authoritative event watermark cannot be negative")
        values = _space_values(space)
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO omnix_memory_v2_authority_streams (
                    principal_id, owner_type, owner_id, last_sequence,
                    observation_watermark, authoritative_event_watermark
                ) VALUES (%s, %s, %s, 0, 0, 0)
                ON CONFLICT (principal_id, owner_type, owner_id) DO NOTHING
                """,
                values,
            )
            row = connection.execute(
                """
                SELECT authoritative_event_watermark
                  FROM omnix_memory_v2_authority_streams
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                 FOR UPDATE
                """,
                values,
            ).fetchone()
            if row is None:  # pragma: no cover
                raise MemoryAuthorityError("failed to establish authority event stream")
            current = int(row[0])
            if watermark < current:
                raise MemoryAuthorityError(
                    "authoritative event watermark cannot move backward"
                )
            connection.execute(
                """
                UPDATE omnix_memory_v2_authority_streams
                   SET authoritative_event_watermark = %s,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                """,
                (watermark, *values),
            )
        return watermark

    def authoritative_event_watermark(self, space: MemorySpaceKey) -> int:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT authoritative_event_watermark
                  FROM omnix_memory_v2_authority_streams
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                """,
                _space_values(space),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def evaluate_space(
        self,
        space: MemorySpaceKey,
        *,
        graph_validation: GraphReplayReport,
    ) -> SpaceCutoverReadinessReceipt:
        authoritative_event = self.authoritative_event_watermark(space)
        observation = self.observation_store.watermark(space)
        governance = self.observation_store.governance_revision(space)
        consolidation = self.consolidator.watermark(space)
        graph_state = self.graph_store.state(space)
        derived_state = self.derived_store.state(space)
        derived_replay = self.derived_replay_validator.validate(space)
        index_status = self.search_index.status(space)
        shadow = self.shadow_store.latest(space)

        graph_replay_passed = (
            graph_validation.matches
            and graph_validation.observation_watermark == observation
            and graph_validation.graph_revision == graph_state.graph_revision
            and graph_validation.persisted_digest == graph_validation.replay_digest
        )
        exact_replay_passed = (
            derived_replay.matches
            and derived_replay.derived_revision == derived_state.derived_revision
            and derived_state.derived_revision > 0
        )
        validation_passed = graph_replay_passed and exact_replay_passed
        shadow_quality_passed = (
            shadow is not None
            and shadow.passed
            and shadow.observation_watermark == observation
            and shadow.graph_revision == graph_state.graph_revision
        )
        derived_caught_up = (
            derived_state.derived_revision > 0
            and derived_state.source_observation_watermark == observation
            and derived_state.source_governance_revision == governance
        )
        indexes_caught_up = (
            derived_caught_up
            and not index_status.stale
            and index_status.state.index_graph_revision == graph_state.graph_revision
            and index_status.state.source_observation_watermark == observation
            and index_status.state.index_derived_revision == derived_state.derived_revision
        )
        graph_caught_up = graph_state.source_observation_watermark == observation
        ready = (
            observation == authoritative_event
            and consolidation == observation
            and graph_caught_up
            and derived_caught_up
            and validation_passed
            and shadow_quality_passed
            and indexes_caught_up
        )
        readiness = CutoverReadiness(
            watermarks=MemoryWatermarks(
                authoritative_event=authoritative_event,
                observation=observation,
                consolidation=consolidation,
                graph_revision=graph_state.graph_revision,
                index_graph_revision=index_status.state.index_graph_revision,
                governance_revision=governance,
                derived_revision=derived_state.derived_revision,
                derived_observation_watermark=derived_state.source_observation_watermark,
                index_derived_revision=index_status.state.index_derived_revision,
            ),
            graph_validation_passed=validation_passed,
            shadow_quality_passed=shadow_quality_passed,
            indexes_caught_up=indexes_caught_up,
            ready=ready,
        )
        receipt_id = f"cutover-readiness:{uuid4()}"
        validation_digest = (
            f"graph:{graph_validation.replay_digest};derived:{derived_replay.replay_digest}"
            if validation_passed
            else None
        )
        with self.database.transaction() as connection:
            row = connection.execute(
                f"""
                INSERT INTO omnix_memory_v2_cutover_readiness_receipts (
                    receipt_id, principal_id, owner_type, owner_id,
                    authoritative_event_watermark, observation_watermark,
                    consolidation_watermark, graph_revision,
                    graph_source_observation_watermark, index_graph_revision,
                    index_source_observation_watermark, index_governance_digest,
                    graph_validation_passed, graph_validation_digest,
                    shadow_evaluation_id, shadow_quality_passed,
                    indexes_caught_up, ready, governance_revision,
                    derived_revision, derived_source_observation_watermark,
                    derived_source_governance_revision, index_derived_revision
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                RETURNING {_READINESS_COLUMNS}
                """,
                (
                    receipt_id,
                    *_space_values(space),
                    readiness.watermarks.authoritative_event,
                    readiness.watermarks.observation,
                    readiness.watermarks.consolidation,
                    readiness.watermarks.graph_revision,
                    graph_state.source_observation_watermark,
                    readiness.watermarks.index_graph_revision,
                    index_status.state.source_observation_watermark,
                    index_status.state.governance_digest,
                    readiness.graph_validation_passed,
                    validation_digest,
                    shadow.evaluation_id if shadow is not None else None,
                    readiness.shadow_quality_passed,
                    readiness.indexes_caught_up,
                    readiness.ready,
                    governance,
                    derived_state.derived_revision,
                    derived_state.source_observation_watermark,
                    derived_state.source_governance_revision,
                    index_status.state.index_derived_revision,
                ),
            ).fetchone()
        if row is None:  # pragma: no cover
            raise MemoryAuthorityError("cutover readiness receipt insert returned no row")
        return _readiness_receipt_from_row(row)

    def get_readiness_receipt(
        self,
        receipt_id: str,
    ) -> SpaceCutoverReadinessReceipt | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                f"""
                SELECT {_READINESS_COLUMNS}
                  FROM omnix_memory_v2_cutover_readiness_receipts
                 WHERE receipt_id = %s
                """,
                (receipt_id,),
            ).fetchone()
        return _readiness_receipt_from_row(row) if row is not None else None

    @staticmethod
    def _epoch_from_row(row: Any) -> AuthorityEpochState:
        readiness_data = dict(row[4]) if row[4] is not None else None
        epoch = MemoryAuthorityEpoch(
            epoch=int(row[0]),
            authority=str(row[1]),
            activated_at=row[2],
            previous_epoch=int(row[3]) if row[3] is not None else None,
            readiness=(
                CutoverReadiness.model_validate(readiness_data)
                if readiness_data is not None
                else None
            ),
            activated_by=str(row[6]),
        )
        return AuthorityEpochState(
            epoch=epoch,
            readiness_receipt_ids=tuple(str(item) for item in row[5]),
            reason=str(row[7]) if row[7] is not None else None,
        )

    def current(self) -> AuthorityEpochState:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT e.epoch, e.authority, e.activated_at, e.previous_epoch,
                       e.readiness, e.readiness_receipt_ids, e.activated_by, e.reason
                  FROM omnix_memory_v2_authority_current c
                  JOIN omnix_memory_v2_authority_epochs e ON e.epoch = c.current_epoch
                 WHERE c.singleton = TRUE
                """
            ).fetchone()
        if row is None:  # pragma: no cover
            raise MemoryAuthorityError("Memory v2 current authority epoch is missing")
        return self._epoch_from_row(row)

    @staticmethod
    def _load_receipt_for_update(connection: Any, receipt_id: str) -> Any:
        row = connection.execute(
            f"""
            SELECT {_READINESS_COLUMNS}
              FROM omnix_memory_v2_cutover_readiness_receipts
             WHERE receipt_id = %s
             FOR UPDATE
            """,
            (receipt_id,),
        ).fetchone()
        if row is None:
            raise CutoverNotReadyError(f"cutover readiness receipt not found: {receipt_id}")
        return row

    @staticmethod
    def _assert_receipt_fresh(connection: Any, receipt: SpaceCutoverReadinessReceipt) -> None:
        if not receipt.readiness.ready:
            raise CutoverNotReadyError(
                f"cutover readiness receipt is not ready: {receipt.receipt_id}"
            )
        values = _space_values(receipt.space)
        stream = connection.execute(
            """
            SELECT authoritative_event_watermark, observation_watermark, governance_revision
              FROM omnix_memory_v2_authority_streams
             WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
             FOR UPDATE
            """,
            values,
        ).fetchone()
        consolidation = connection.execute(
            """
            SELECT consolidation_watermark
              FROM omnix_memory_v2_consolidation_state
             WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
             FOR UPDATE
            """,
            values,
        ).fetchone()
        graph = connection.execute(
            """
            SELECT graph_revision, source_observation_watermark
              FROM omnix_memory_v2_graph_state
             WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
             FOR UPDATE
            """,
            values,
        ).fetchone()
        derived = connection.execute(
            """
            SELECT derived_revision, source_observation_watermark,
                   source_governance_revision
              FROM omnix_memory_v2_derived_state
             WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
             FOR UPDATE
            """,
            values,
        ).fetchone()
        index_state = connection.execute(
            """
            SELECT index_graph_revision, source_observation_watermark,
                   governance_digest, index_derived_revision
              FROM omnix_memory_v2_search_index_state
             WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
             FOR UPDATE
            """,
            values,
        ).fetchone()
        latest_shadow = connection.execute(
            """
            SELECT evaluation_id, observation_watermark, graph_revision, passed
              FROM omnix_memory_v2_shadow_evaluations
             WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
             ORDER BY created_at DESC, evaluation_id DESC
             LIMIT 1
             FOR UPDATE
            """,
            values,
        ).fetchone()
        if any(
            item is None
            for item in (
                stream,
                consolidation,
                graph,
                derived,
                index_state,
                latest_shadow,
            )
        ):
            raise StaleCutoverReceiptError(
                f"cutover state disappeared after readiness evaluation: {receipt.receipt_id}"
            )

        marks = receipt.readiness.watermarks
        current_governance_digest = PostgresMemoryV2SearchIndex._governance_digest(
            connection,
            receipt.space,
        )
        current = (
            int(stream[0]),
            int(stream[1]),
            int(stream[2]),
            int(consolidation[0]),
            int(graph[0]),
            int(graph[1]),
            int(derived[0]),
            int(derived[1]),
            int(derived[2]),
            int(index_state[0]),
            int(index_state[1]),
            str(index_state[2]),
            int(index_state[3]),
            current_governance_digest,
            str(latest_shadow[0]),
            int(latest_shadow[1]),
            int(latest_shadow[2]),
            bool(latest_shadow[3]),
        )
        expected = (
            marks.authoritative_event,
            marks.observation,
            receipt.governance_revision,
            marks.consolidation,
            marks.graph_revision,
            receipt.graph_source_observation_watermark,
            receipt.derived_revision,
            receipt.derived_source_observation_watermark,
            receipt.derived_source_governance_revision,
            marks.index_graph_revision,
            receipt.index_source_observation_watermark,
            receipt.index_governance_digest,
            receipt.index_derived_revision,
            receipt.index_governance_digest,
            receipt.shadow_evaluation_id,
            marks.observation,
            marks.graph_revision,
            True,
        )
        if current != expected:
            raise StaleCutoverReceiptError(
                f"cutover readiness receipt is stale: {receipt.receipt_id}"
            )

    def activate_v2(
        self,
        readiness_receipt_ids: tuple[str, ...],
        *,
        activated_by: str,
        reason: str | None = None,
    ) -> AuthorityEpochState:
        receipt_ids = tuple(dict.fromkeys(readiness_receipt_ids))
        if not receipt_ids:
            raise CutoverNotReadyError("at least one ready memory space is required for cutover")
        if len(receipt_ids) != len(readiness_receipt_ids):
            raise CutoverNotReadyError("duplicate readiness receipts are not allowed")
        if not activated_by:
            raise ValueError("activated_by is required")

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
                raise MemoryAuthorityError("Memory v2 current authority epoch is missing")
            current = self._epoch_from_row(current_row)
            if current.epoch.authority == "v2":
                return current
            if current.epoch.authority != "v1":  # pragma: no cover
                raise MemoryAuthorityError("unsupported current memory authority")

            receipts = [
                _readiness_receipt_from_row(
                    self._load_receipt_for_update(connection, receipt_id)
                )
                for receipt_id in receipt_ids
            ]
            spaces = [receipt.space for receipt in receipts]
            if len(set(spaces)) != len(spaces):
                raise CutoverNotReadyError(
                    "cutover requires exactly one readiness receipt per space"
                )
            for receipt in receipts:
                self._assert_receipt_fresh(connection, receipt)

            aggregate = CutoverReadiness(
                watermarks=MemoryWatermarks(
                    authoritative_event=sum(
                        item.readiness.watermarks.authoritative_event for item in receipts
                    ),
                    observation=sum(
                        item.readiness.watermarks.observation for item in receipts
                    ),
                    consolidation=sum(
                        item.readiness.watermarks.consolidation for item in receipts
                    ),
                    graph_revision=sum(
                        item.readiness.watermarks.graph_revision for item in receipts
                    ),
                    index_graph_revision=sum(
                        item.readiness.watermarks.index_graph_revision for item in receipts
                    ),
                    governance_revision=sum(
                        item.governance_revision for item in receipts
                    ),
                    derived_revision=sum(item.derived_revision for item in receipts),
                    derived_observation_watermark=sum(
                        item.derived_source_observation_watermark for item in receipts
                    ),
                    index_derived_revision=sum(
                        item.index_derived_revision for item in receipts
                    ),
                ),
                graph_validation_passed=True,
                shadow_quality_passed=True,
                indexes_caught_up=True,
                ready=True,
            )
            max_epoch_row = connection.execute(
                "SELECT COALESCE(MAX(epoch), 0) FROM omnix_memory_v2_authority_epochs"
            ).fetchone()
            next_epoch = int(max_epoch_row[0]) + 1
            activated_at = datetime.now(timezone.utc)
            epoch = MemoryAuthorityEpoch(
                epoch=next_epoch,
                authority="v2",
                activated_at=activated_at,
                previous_epoch=current.epoch.epoch,
                readiness=aggregate,
                activated_by=activated_by,
            )
            connection.execute(
                """
                INSERT INTO omnix_memory_v2_authority_epochs (
                    epoch, authority, activated_at, previous_epoch, readiness,
                    readiness_receipt_ids, activated_by, reason
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                """,
                (
                    epoch.epoch,
                    epoch.authority,
                    epoch.activated_at,
                    epoch.previous_epoch,
                    _json(aggregate.model_dump(mode="json")),
                    _json(receipt_ids),
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
            readiness_receipt_ids=receipt_ids,
            reason=reason,
        )
