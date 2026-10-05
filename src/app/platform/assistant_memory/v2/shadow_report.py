"""Memory v2 shadow-comparison report for the authority cutover (WP-8.5).

The v1 -> v2 authority flip is a human decision. This report gathers what that
decision needs from the existing tables, without writing anything:

- the current authority epoch;
- for every v2 memory space: its watermarks, latest shadow retrieval
  evaluation and latest cutover readiness receipt;
- v1 owners with memories but no v2 space yet (not imported).

The shadow runner (``python -m app.platform.assistant_memory.v2.shadow_runner``)
produces the evaluations and receipts. Run it as an operator command::

    python -m app.platform.assistant_memory.v2.shadow_report [--require-ready]

A space's ``status`` is one of ``not_evaluated``, ``v1_changed`` (the
owner's v1 records differ from what v2 holds: run the shadow runner
again), ``evaluation_stale`` (the space received observations after its
evaluation), ``shadow_failed``, ``not_ready`` (the evaluation passed but no
current ready receipt exists) and ``ready``. ``ready`` is advisory:
activation re-checks every receipt under lock, so a receipt can still be
refused as stale.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from app.persistence.database import PostgresDatabase, default_database
from app.persistence.tenant_scope import system_scope

SPACE_STATUSES = ("not_evaluated", "v1_changed", "evaluation_stale", "shadow_failed", "not_ready", "ready")
_UNIMPORTED_LIST_LIMIT = 50


@dataclass(frozen=True)
class ShadowEvaluationSummary:
    evaluation_id: str
    observation_watermark: int
    graph_revision: int
    v1_result_count: int
    v2_result_count: int
    matched_v1_count: int
    recall: float
    precision: float
    passed: bool
    created_at: str


@dataclass(frozen=True)
class ReadinessSummary:
    receipt_id: str
    authoritative_event_watermark: int
    observation_watermark: int
    graph_validation_passed: bool
    shadow_quality_passed: bool
    indexes_caught_up: bool
    ready: bool
    created_at: str


@dataclass(frozen=True)
class SpaceShadowStatus:
    principal_id: str
    owner_type: str
    owner_id: str
    authoritative_event_watermark: int
    observation_watermark: int
    status: str
    evaluation: ShadowEvaluationSummary | None
    readiness: ReadinessSummary | None


@dataclass(frozen=True)
class UnimportedOwner:
    owner_type: str
    owner_id: str
    active_v1_records: int


@dataclass(frozen=True)
class MemoryV2ShadowReport:
    authority: str
    epoch: int
    spaces: tuple[SpaceShadowStatus, ...]
    status_counts: dict[str, int]
    unimported_v1_owner_count: int
    unimported_v1_owners: tuple[UnimportedOwner, ...]
    all_spaces_ready: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _space_status(
    *,
    authoritative_event: int,
    observation: int,
    evaluation: ShadowEvaluationSummary | None,
    readiness: ReadinessSummary | None,
    v1_changed: bool = False,
) -> str:
    if evaluation is None:
        return "not_evaluated"
    if v1_changed:
        return "v1_changed"
    if evaluation.observation_watermark != observation:
        return "evaluation_stale"
    if not evaluation.passed:
        return "shadow_failed"
    if (
        readiness is None
        or not readiness.ready
        or readiness.observation_watermark != observation
        or readiness.authoritative_event_watermark != authoritative_event
    ):
        return "not_ready"
    return "ready"


_SPACES_SQL = """
SELECT s.principal_id, s.owner_type, s.owner_id,
       s.authoritative_event_watermark, s.observation_watermark,
       ev.evaluation_id, ev.observation_watermark, ev.graph_revision,
       ev.v1_result_count, ev.v2_result_count, ev.matched_v1_count,
       ev.recall, ev.precision, ev.passed, ev.created_at,
       rc.receipt_id, rc.authoritative_event_watermark, rc.observation_watermark,
       rc.graph_validation_passed, rc.shadow_quality_passed, rc.indexes_caught_up,
       rc.ready, rc.created_at
  FROM omnix_memory_v2_authority_streams s
  LEFT JOIN LATERAL (
      SELECT e.*
        FROM omnix_memory_v2_shadow_evaluations e
       WHERE e.principal_id = s.principal_id
         AND e.owner_type = s.owner_type
         AND e.owner_id = s.owner_id
       ORDER BY e.created_at DESC, e.evaluation_id DESC
       LIMIT 1
  ) ev ON TRUE
  LEFT JOIN LATERAL (
      SELECT r.*
        FROM omnix_memory_v2_cutover_readiness_receipts r
       WHERE r.principal_id = s.principal_id
         AND r.owner_type = s.owner_type
         AND r.owner_id = s.owner_id
       ORDER BY r.created_at DESC, r.receipt_id DESC
       LIMIT 1
  ) rc ON TRUE
 ORDER BY s.principal_id, s.owner_type, s.owner_id
"""

UNIMPORTED_V1_OWNERS_SQL = """
SELECT r.owner_type, r.owner_id, COUNT(*)
  FROM omnix_memory_records r
 WHERE NOT EXISTS (
       SELECT 1
         FROM omnix_memory_v2_authority_streams s
        WHERE s.owner_type = r.owner_type
          AND s.owner_id = r.owner_id
   )
 GROUP BY r.owner_type, r.owner_id
 ORDER BY COUNT(*) DESC, r.owner_type, r.owner_id
"""

# Owners whose v1 records (any status; id and revision) differ from the
# active imported observations across their v2 spaces. The shadow runner
# imports every record; what may reach a prompt is decided at projection.
V1_CHANGED_SQL = """
WITH v1 AS (
    SELECT owner_type, owner_id, id, revision
      FROM omnix_memory_records
), imported AS (
    SELECT o.owner_type, o.owner_id,
           o.payload->'legacy_record'->>'id' AS id,
           (o.payload->'legacy_record'->>'revision')::BIGINT AS revision
      FROM omnix_memory_v2_observations o
      LEFT JOIN omnix_memory_v2_observation_dispositions d
        ON d.observation_id = o.observation_id
     WHERE o.event_type = 'imported_legacy_memory'
       AND COALESCE(d.state, 'active') = 'active'
)
SELECT owner_type, owner_id FROM (
    (SELECT * FROM v1 EXCEPT SELECT * FROM imported)
    UNION ALL
    (SELECT * FROM imported EXCEPT SELECT * FROM v1)
) changed
GROUP BY owner_type, owner_id
"""

_EPOCH_SQL = """
SELECT e.epoch, e.authority
  FROM omnix_memory_v2_authority_current c
  JOIN omnix_memory_v2_authority_epochs e ON e.epoch = c.current_epoch
 WHERE c.singleton = TRUE
"""


def _space_from_row(row: Sequence[Any], v1_changed: set[tuple[str, str]]) -> SpaceShadowStatus:
    evaluation = None
    if row[5] is not None:
        evaluation = ShadowEvaluationSummary(
            evaluation_id=str(row[5]),
            observation_watermark=int(row[6]),
            graph_revision=int(row[7]),
            v1_result_count=int(row[8]),
            v2_result_count=int(row[9]),
            matched_v1_count=int(row[10]),
            recall=float(row[11]),
            precision=float(row[12]),
            passed=bool(row[13]),
            created_at=row[14].isoformat(),
        )
    readiness = None
    if row[15] is not None:
        readiness = ReadinessSummary(
            receipt_id=str(row[15]),
            authoritative_event_watermark=int(row[16]),
            observation_watermark=int(row[17]),
            graph_validation_passed=bool(row[18]),
            shadow_quality_passed=bool(row[19]),
            indexes_caught_up=bool(row[20]),
            ready=bool(row[21]),
            created_at=row[22].isoformat(),
        )
    authoritative_event, observation = int(row[3]), int(row[4])
    return SpaceShadowStatus(
        principal_id=str(row[0]),
        owner_type=str(row[1]),
        owner_id=str(row[2]),
        authoritative_event_watermark=authoritative_event,
        observation_watermark=observation,
        status=_space_status(
            authoritative_event=authoritative_event,
            observation=observation,
            evaluation=evaluation,
            readiness=readiness,
            v1_changed=(str(row[1]), str(row[2])) in v1_changed,
        ),
        evaluation=evaluation,
        readiness=readiness,
    )


def build_shadow_report(database: PostgresDatabase) -> MemoryV2ShadowReport:
    """Read the report across every workspace (an operator command)."""
    with system_scope("operator.cli"), database.transaction() as connection:
        epoch_row = connection.execute(_EPOCH_SQL).fetchone()
        if epoch_row is None:
            raise RuntimeError("Memory v2 current authority epoch is missing")
        v1_changed = {(str(row[0]), str(row[1])) for row in connection.execute(V1_CHANGED_SQL).fetchall()}
        spaces = tuple(_space_from_row(row, v1_changed) for row in connection.execute(_SPACES_SQL).fetchall())
        unimported = [
            UnimportedOwner(owner_type=str(row[0]), owner_id=str(row[1]), active_v1_records=int(row[2]))
            for row in connection.execute(UNIMPORTED_V1_OWNERS_SQL).fetchall()
        ]
    counts = Counter(space.status for space in spaces)
    return MemoryV2ShadowReport(
        authority=str(epoch_row[1]),
        epoch=int(epoch_row[0]),
        spaces=spaces,
        status_counts={status: counts.get(status, 0) for status in SPACE_STATUSES},
        unimported_v1_owner_count=len(unimported),
        unimported_v1_owners=tuple(unimported[:_UNIMPORTED_LIST_LIMIT]),
        all_spaces_ready=bool(spaces) and not unimported and counts.get("ready", 0) == len(spaces),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report Memory v2 shadow comparison and cutover readiness.")
    parser.add_argument(
        "--require-ready", action="store_true",
        help="exit 1 unless every space is ready and every v1 owner is imported",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    database = default_database()
    try:
        report = build_shadow_report(database)
    finally:
        database.close()
    sys.stdout.write(json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n")
    return 1 if args.require_ready and not report.all_spaces_ready else 0


if __name__ == "__main__":
    raise SystemExit(main())
