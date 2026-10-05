"""Memory v2 shadow runner: bring every v1 memory owner to a cutover verdict (WP-8.5).

While v1 is authoritative, this operator command does, for each memory space:

1. **Import**: each v1 record, whatever its status, becomes an
   ``imported_legacy_memory`` observation (idempotent per record revision),
   so archived, secret and unapproved records stay manageable after the
   cutover. A revision v1 replaced is revoked; a record v1 deleted
   (forgotten) is purged, so its text leaves Memory v2 as well.
2. **Derive and index**: the curated projector derives one assertion per
   record v1 would let reach a prompt (active, not secret, approved; ending
   at its expiry), with no model involved; then the search index is rebuilt
   and the embeddings synced (retrieval falls back to words without them).
3. **Compare**: up to ``--probes`` of those prompt-eligible records are asked
   of v2 by their own words, under the record's scope plus the profile's
   global scope. Recall counts probes whose record came back; precision
   counts returned memories backed only by eligible, visible v1 records
   (see ``compare_shadow_probes``).
4. **Evaluate**: graph replay, then a cutover readiness receipt.

Run it, then read the verdict with the report::

    python -m app.assistant_memory.v2.shadow_runner [--probes 200]
    python -m app.assistant_memory.v2.shadow_report --require-ready

Pre-cutover, the runner is the authoritative feed into v2: a space's
authoritative event watermark is advanced to its observation watermark after
each sync. The report separately flags owners whose v1 records changed since
the last run. The runner never activates v2; that flip is a human decision.

A v2 memory space is a tenant workspace's owner (``principal_id`` is the
tenant workspace id), the same key v1 records have; profile, chat workspace,
project and session stay visibility scopes. An owner with a v1 row the v1
contract rejects is skipped and listed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.memory_contracts import MemoryRecord, record_prompt_block_reason
from app.persistence.database import PostgresDatabase, default_database
from app.persistence.tenant_scope import system_scope

from .contracts import MemorySpaceKey, RetrievalQuery, VisibilityScope
from .convergence import DerivedPlanPayload, PostgresMemoryV2DerivedCoordinator
from .graph_store import GraphReplayValidator
from .legacy_shadow import (
    LegacyMemoryV2Importer,
    ShadowProbe,
    compare_shadow_probes,
    legacy_observation_id,
    legacy_seed_projector,
)
from .runtime import PostgresMemoryV2Runtime

CONSOLIDATOR_VERSION = "memory-v2-shadow-runner@1"
RUNNER_ACTOR = "operator:memory-v2-shadow-runner"
_PAGE_SIZE = 1000
# Chat's defaults: top 12 memories within the 4,000-token memory budget, 50 ms deadline.
DEFAULT_TOP_K = 12
DEFAULT_TOKEN_BUDGET = 4000
DEFAULT_DEADLINE_MS = 50.0
_LOCK_KEY = "omnix.memory_v2.shadow_runner"

_V1_COLUMNS = """
id, workspace_id, owner_type, owner_id, scope, scope_id, category, kind,
structured_payload, supersedes_memory_id, contradiction_group, content,
normalized_content, confidence, pinned, trust_level, sensitivity,
provenance_type, provenance_id, source, status, revision, created_at,
updated_at, expires_at
"""


class ShadowRunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class V1Row:
    workspace_id: str
    record: MemoryRecord


@dataclass(frozen=True)
class InvalidV1Row:
    record_id: str
    owner_type: str
    owner_id: str


@dataclass
class SpaceRunOutcome:
    principal_id: str
    owner_type: str
    owner_id: str
    imported: int = 0
    revoked: int = 0
    purged: int = 0
    reactivated: int = 0
    probes: int = 0
    recall: float | None = None
    precision: float | None = None
    shadow_passed: bool | None = None
    graph_validation_passed: bool | None = None
    ready: bool = False
    receipt_id: str | None = None
    # synced, model_absent (retrieval by words) or sync_failed
    embeddings: str | None = None
    error: str | None = None


@dataclass
class ShadowRunReport:
    authority: str
    spaces: list[SpaceRunOutcome] = field(default_factory=list)
    skipped_owners: list[dict[str, Any]] = field(default_factory=list)

    @property
    def all_ready(self) -> bool:
        return bool(self.spaces) and not self.skipped_owners and all(item.ready for item in self.spaces)

    def as_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "all_ready": self.all_ready,
            "ready_spaces": sum(item.ready for item in self.spaces),
            "spaces": [asdict(item) for item in self.spaces],
            "skipped_owners": self.skipped_owners,
        }


def _record_from_row(row: Sequence[Any]) -> MemoryRecord:
    return MemoryRecord(
        id=str(row[0]),
        owner_type=str(row[2]),
        owner_id=str(row[3]),
        scope=str(row[4]),
        scope_id=str(row[5]),
        category=str(row[6]),
        kind=str(row[7]),
        structured_payload=dict(row[8] or {}),
        supersedes_memory_id=str(row[9]) if row[9] is not None else None,
        contradiction_group=str(row[10]) if row[10] is not None else None,
        content=str(row[11]),
        normalized_content=str(row[12]),
        confidence=float(row[13]),
        pinned=bool(row[14]),
        trust_level=str(row[15]),
        sensitivity=str(row[16]),
        provenance_type=str(row[17]) if row[17] is not None else None,
        provenance_id=str(row[18]) if row[18] is not None else None,
        source=str(row[19]),
        status=str(row[20]),
        revision=int(row[21]),
        created_at=row[22].isoformat(),
        updated_at=row[23].isoformat(),
        expires_at=row[24].isoformat() if row[24] is not None else None,
    )


def load_v1_rows(database: PostgresDatabase) -> tuple[list[V1Row], list[InvalidV1Row]]:
    """Every v1 record in every workspace, any status, in id pages.

    A row the v1 contract rejects (written outside v1's code) cannot be
    imported faithfully; it is returned separately so its owner is skipped.
    """
    rows: list[V1Row] = []
    invalid: list[InvalidV1Row] = []
    after = ""
    with system_scope("operator.cli"):
        while True:
            with database.transaction() as connection:
                page = connection.execute(
                    f"SELECT {_V1_COLUMNS} FROM omnix_memory_records WHERE id > %s ORDER BY id LIMIT %s",
                    (after, _PAGE_SIZE),
                ).fetchall()
            for row in page:
                try:
                    rows.append(V1Row(workspace_id=str(row[1]), record=_record_from_row(row)))
                except ValidationError:
                    invalid.append(InvalidV1Row(record_id=str(row[0]), owner_type=str(row[2]), owner_id=str(row[3])))
            if len(page) < _PAGE_SIZE:
                return rows, invalid
            after = str(page[-1][0])


@dataclass(frozen=True)
class ImportedObservation:
    observation_id: str
    record_id: str | None
    revision: int | None
    state: str


def load_imported(database: PostgresDatabase) -> dict[MemorySpaceKey, list[ImportedObservation]]:
    """Every imported v1 observation in Memory v2 with its disposition, by space."""
    imported: dict[MemorySpaceKey, list[ImportedObservation]] = defaultdict(list)
    after = ""
    while True:
        with database.transaction() as connection:
            page = connection.execute(
                """
                SELECT o.observation_id, o.principal_id, o.owner_type, o.owner_id,
                       o.payload->'legacy_record'->>'id',
                       o.payload->'legacy_record'->>'revision',
                       COALESCE(d.state, 'active')
                  FROM omnix_memory_v2_observations o
                  LEFT JOIN omnix_memory_v2_observation_dispositions d
                    ON d.observation_id = o.observation_id
                 WHERE o.event_type = 'imported_legacy_memory' AND o.observation_id > %s
                 ORDER BY o.observation_id
                 LIMIT %s
                """,
                (after, _PAGE_SIZE),
            ).fetchall()
        for row in page:
            space = MemorySpaceKey(principal_id=str(row[1]), owner_type=str(row[2]), owner_id=str(row[3]))
            imported[space].append(
                ImportedObservation(
                    observation_id=str(row[0]),
                    record_id=str(row[4]) if row[4] is not None else None,
                    revision=int(row[5]) if row[5] is not None else None,
                    state=str(row[6]),
                )
            )
        if len(page) < _PAGE_SIZE:
            return dict(imported)
        after = str(page[-1][0])


def _prompt_eligible(record: MemoryRecord, now: datetime) -> bool:
    """Whether v1 would put this record in front of the model (scope aside)."""
    return record_prompt_block_reason(record, now) is None


def _legacy_planner(
    _space: MemorySpaceKey,
    window: tuple[Any, ...],
    _existing: tuple[Any, ...],
) -> DerivedPlanPayload:
    return DerivedPlanPayload(
        assertions=legacy_seed_projector(window),
        consolidator_version=CONSOLIDATOR_VERSION,
    )


def _profile_of(records: list[MemoryRecord], record: MemoryRecord) -> str:
    """The profile a question about ``record`` is asked from.

    A global record names its profile. Otherwise the space's single global
    profile when there is one; with none (or several) the record's own scope
    alone decides what is visible.
    """
    if record.scope == "global":
        return record.scope_id
    profiles = {item.scope_id for item in records if item.scope == "global"}
    return next(iter(profiles)) if len(profiles) == 1 else record.scope_id


def _probe_order(record: MemoryRecord) -> str:
    return hashlib.sha256(record.id.encode("utf-8")).hexdigest()


class MemoryV2ShadowRunner:
    def __init__(
        self,
        database: PostgresDatabase,
        *,
        runtime: PostgresMemoryV2Runtime | None = None,
        probes: int = 200,
        top_k: int = DEFAULT_TOP_K,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        deadline_ms: float = DEFAULT_DEADLINE_MS,
        required_recall: float = 0.95,
        required_precision: float = 1.0,
        owners: set[tuple[str, str]] | None = None,
        now: datetime | None = None,
    ) -> None:
        self.database = database
        self.runtime = runtime or PostgresMemoryV2Runtime(database)
        self.authority = self.runtime.authority_store
        self.observations = self.runtime.observation_store
        self.graph = self.runtime.graph_store
        self.search = self.runtime.search_index
        self.coordinator = PostgresMemoryV2DerivedCoordinator(
            database,
            observation_store=self.observations,
            graph_store=self.graph,
            derived_store=self.runtime.derived_store,
        )
        self.importer = LegacyMemoryV2Importer(self.observations)
        self.probes = max(0, int(probes))
        self.top_k = top_k
        self.token_budget = token_budget
        self.deadline_ms = deadline_ms
        self.required_recall = required_recall
        self.required_precision = required_precision
        self.owners = owners
        self.now = now

    def run(self) -> ShadowRunReport:
        authority = self.runtime.current().epoch.authority
        if authority != "v1":
            raise ShadowRunnerError(
                f"the shadow runner only runs while v1 is authoritative (current authority: {authority})"
            )
        now = self.now or datetime.now(timezone.utc)
        report = ShadowRunReport(authority=authority)
        v1_rows, invalid_rows = load_v1_rows(self.database)
        known_ids = {row.record.id for row in v1_rows} | {row.record_id for row in invalid_rows}
        if self.owners is not None:
            v1_rows = [row for row in v1_rows if (row.record.owner_type, row.record.owner_id) in self.owners]
            invalid_rows = [row for row in invalid_rows if (row.owner_type, row.owner_id) in self.owners]

        invalid: dict[tuple[str, str], int] = defaultdict(int)
        for row in invalid_rows:
            invalid[(row.owner_type, row.owner_id)] += 1
        skipped = set(invalid)
        for owner_type, owner_id in sorted(skipped):
            report.skipped_owners.append({
                "owner_type": owner_type,
                "owner_id": owner_id,
                "reason": "invalid_v1_records",
                "invalid_record_count": invalid[(owner_type, owner_id)],
            })

        serving: dict[MemorySpaceKey, list[MemoryRecord]] = defaultdict(list)
        for row in v1_rows:
            record = row.record
            if (record.owner_type, record.owner_id) in skipped:
                continue
            serving[self.importer.space_for(row.workspace_id, record)].append(record)

        imported = load_imported(self.database)
        if self.owners is not None:
            imported = {space: items for space, items in imported.items()
                        if (space.owner_type, space.owner_id) in self.owners}
        spaces = sorted(
            {*serving, *(space for space in imported if (space.owner_type, space.owner_id) not in skipped)},
            key=lambda item: (item.principal_id, item.owner_type, item.owner_id),
        )
        if spaces:
            self._warm_up(spaces[0], now)
        for space in spaces:
            outcome = SpaceRunOutcome(space.principal_id, space.owner_type, space.owner_id)
            try:
                self._run_space(space, serving.get(space, []), imported.get(space, []), known_ids, now, outcome)
            except Exception as exc:  # noqa: BLE001 - one bad space must not hide the others' verdicts
                outcome.error = f"{type(exc).__name__}: {exc}"
            report.spaces.append(outcome)
        return report

    def _warm_up(self, space: MemorySpaceKey, now: datetime) -> None:
        """Load the embedding model before timed probes; its first use takes seconds."""
        self.runtime.local_retriever.retrieve(RetrievalQuery(
            query_id="shadow-runner:warm-up",
            space=space,
            visible_scopes=(VisibilityScope(kind="global", scope_id=space.principal_id),),
            text="warm up",
            authority="final",
            as_of=now,
            top_k=1,
            token_budget=self.token_budget,
            deadline_ms=10_000.0,
        ))

    def _sync(
        self,
        space: MemorySpaceKey,
        records: list[MemoryRecord],
        imported: list[ImportedObservation],
        known_ids: set[str],
        outcome: SpaceRunOutcome,
    ) -> None:
        wanted = {(record.id, record.revision) for record in records}
        present = set()
        for item in imported:
            if item.record_id is None or item.state == "purged":
                continue
            key = (item.record_id, item.revision)
            present.add(key)
            if key in wanted:
                desired = "active"
            elif item.record_id not in known_ids:
                desired = "purged"
            else:
                desired = "revoked"
            if desired == item.state:
                continue
            self.observations.set_disposition(
                space,
                item.observation_id,
                state=desired,
                actor_id=RUNNER_ACTOR,
                reason={
                    "active": "v1 holds this record revision again",
                    "revoked": "v1 replaced this record revision",
                    "purged": "v1 forgot this record",
                }[desired],
            )
            if desired == "active":
                outcome.reactivated += 1
            elif desired == "revoked":
                outcome.revoked += 1
            else:
                outcome.purged += 1
        for record in records:
            if (record.id, record.revision) not in present:
                self.importer.import_record(principal_id=space.principal_id, record=record, include_inactive=True)
                outcome.imported += 1
        self.authority.advance_authoritative_event_watermark(space, self.observations.watermark(space))

    def _derive_and_index(self, space: MemorySpaceKey, outcome: SpaceRunOutcome) -> None:
        prepared = self.coordinator.prepare(space, _legacy_planner)
        if prepared is not None:
            self.coordinator.commit(prepared)
        self.search.rebuild(space)
        from .embedding_index import PostgresMemoryV2EmbeddingIndex

        index = PostgresMemoryV2EmbeddingIndex(self.database)
        if index.embedder_provider() is None:
            outcome.embeddings = "model_absent"
            return
        try:
            index.sync(space)
            outcome.embeddings = "synced"
        except Exception:  # noqa: BLE001 - retrieval falls back to words, which the probes then measure
            outcome.embeddings = "sync_failed"

    def _probe(self, space: MemorySpaceKey, records: list[MemoryRecord], now: datetime) -> list[ShadowProbe]:
        records = [record for record in records if _prompt_eligible(record, now)]
        evidence = {
            legacy_observation_id(space, record.id, record.revision): (record.scope, record.scope_id)
            for record in records
        }
        probes: list[ShadowProbe] = []
        for record in sorted(records, key=_probe_order)[: self.probes]:
            scopes = tuple(dict.fromkeys((
                VisibilityScope(kind="global", scope_id=_profile_of(records, record)),
                VisibilityScope(kind=record.scope, scope_id=record.scope_id),
            )))
            visible = {(scope.kind, scope.scope_id) for scope in scopes}
            target = legacy_observation_id(space, record.id, record.revision)
            result = self.runtime.local_retriever.retrieve(RetrievalQuery(
                query_id=f"shadow-probe:{target}"[:200],
                space=space,
                visible_scopes=scopes,
                text=record.content,
                authority="final",
                as_of=now,
                top_k=self.top_k,
                token_budget=self.token_budget,
                deadline_ms=self.deadline_ms,
            ))
            probes.append(ShadowProbe(
                target_observation_id=target,
                target_content=record.content,
                allowed_observation_ids=frozenset(
                    observation_id for observation_id, scope in evidence.items() if scope in visible
                ),
                result=result,
            ))
        return probes

    def _run_space(
        self,
        space: MemorySpaceKey,
        records: list[MemoryRecord],
        imported: list[ImportedObservation],
        known_ids: set[str],
        now: datetime,
        outcome: SpaceRunOutcome,
    ) -> None:
        self._sync(space, records, imported, known_ids, outcome)
        self._derive_and_index(space, outcome)
        probes = self._probe(space, records, now)
        evaluation = compare_shadow_probes(
            space=space,
            probes=probes,
            observation_watermark=self.observations.watermark(space),
            graph_revision=self.graph.state(space).graph_revision,
            required_recall=self.required_recall,
            required_precision=self.required_precision,
        )
        self.authority.shadow_store.record(evaluation)
        replay = GraphReplayValidator(self.graph, self.observations).validate(space, legacy_seed_projector)
        receipt = self.authority.evaluate_space(space, graph_validation=replay)
        outcome.probes = len(probes)
        outcome.recall = evaluation.recall
        outcome.precision = evaluation.precision
        outcome.shadow_passed = evaluation.passed
        outcome.graph_validation_passed = receipt.readiness.graph_validation_passed
        outcome.ready = receipt.readiness.ready
        outcome.receipt_id = receipt.receipt_id


@contextmanager
def _exclusive(database: PostgresDatabase) -> Iterator[None]:
    """One runner at a time: a session advisory lock held for the whole run."""
    with database.dedicated_connection() as connection:
        acquired = connection.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (_LOCK_KEY,)).fetchone()[0]
        connection.commit()
        if not acquired:
            raise ShadowRunnerError("another Memory v2 shadow run is in progress")
        # Closing the dedicated connection releases the lock.
        yield


def run_shadow(database: PostgresDatabase, **options: Any) -> ShadowRunReport:
    with _exclusive(database):
        return MemoryV2ShadowRunner(database, **options).run()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import v1 memory into Memory v2, compare, and evaluate readiness.")
    parser.add_argument("--probes", type=int, default=200, help="records asked of v2 per space (default 200)")
    parser.add_argument("--required-recall", type=float, default=0.95)
    parser.add_argument("--required-precision", type=float, default=1.0)
    parser.add_argument("--deadline-ms", type=float, default=DEFAULT_DEADLINE_MS,
                        help="retrieval deadline per probe; Chat uses 50 ms")
    parser.add_argument("--owner", action="append", metavar="TYPE:ID",
                        help="run only this memory owner (repeatable), e.g. character:sofia")
    args = parser.parse_args(list(argv) if argv is not None else None)
    owners = None
    if args.owner:
        owners = set()
        for value in args.owner:
            owner_type, _, owner_id = value.partition(":")
            if owner_type not in {"system", "character"} or not owner_id:
                parser.error(f"--owner must be system:<id> or character:<id>, got {value!r}")
            owners.add((owner_type, owner_id))
    database = default_database()
    try:
        report = run_shadow(
            database,
            probes=args.probes,
            required_recall=args.required_recall,
            required_precision=args.required_precision,
            deadline_ms=args.deadline_ms,
            owners=owners,
        )
    except ShadowRunnerError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    finally:
        database.close()
    sys.stdout.write(json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n")
    return 0 if report.all_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
