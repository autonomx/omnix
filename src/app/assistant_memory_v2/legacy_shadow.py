from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.assistant_memory.models import MemoryRecord
from app.persistence.database import PostgresDatabase, default_database

from .contracts import (
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemoryDomain,
    MemorySpaceKey,
    Observation,
    ObservationProvenance,
    RetrievalResult,
    VisibilityScope,
)
from .graph_store import PostgresMemoryV2GraphStore
from .observation_store import (
    ObservationAppendRequest,
    PostgresMemoryV2ObservationStore,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_TRUST_MAP = {
    "user_approved": "user_explicit",
    "system_trusted": "system_trusted",
    "unverified_import": "imported_unverified",
    "unverified_agent": "assistant_inference",
    "external_untrusted": "external_untrusted",
}

_KIND_DOMAIN_MAP: dict[str, MemoryDomain] = {
    "semantic_fact": "fact",
    "preference": "preference",
    "instruction": "instruction",
    "relationship_state": "relationship",
    "episode": "episode",
    "routine": "routine",
    "goal": "goal",
    "open_loop": "open_loop",
    "temporal_fact": "temporal",
    "pronunciation": "fact",
}


def _space_values(space: MemorySpaceKey) -> tuple[str, str, str]:
    return space.principal_id, space.owner_type, space.owner_id


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _legacy_digest(space: MemorySpaceKey, record_id: str, revision: int) -> str:
    material = f"{space.principal_id}\0{space.owner_type}\0{space.owner_id}\0{record_id}\0{revision}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _jaccard(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens and not right_tokens:
        return 1.0
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


@dataclass(frozen=True, slots=True)
class ShadowRetrievalQualityReport:
    evaluation_id: str
    space: MemorySpaceKey
    observation_watermark: int
    graph_revision: int
    v1_result_count: int
    v2_result_count: int
    matched_v1_count: int
    recall: float
    precision: float
    mean_best_similarity: float
    similarity_threshold: float
    passed: bool


class LegacyMemoryV2Importer:
    """Import curated v1 memory as provenance-preserving v2 evidence observations."""

    def __init__(self, observation_store: PostgresMemoryV2ObservationStore) -> None:
        self.observation_store = observation_store

    @staticmethod
    def space_for(principal_id: str, record: MemoryRecord) -> MemorySpaceKey:
        return MemorySpaceKey(
            principal_id=principal_id,
            owner_type=record.owner_type,
            owner_id=record.owner_id,
        )

    def import_record(
        self,
        *,
        principal_id: str,
        record: MemoryRecord,
    ) -> Observation | None:
        if record.status != "active":
            return None
        space = self.space_for(principal_id, record)
        digest = _legacy_digest(space, record.id, record.revision)
        trust = _TRUST_MAP[record.trust_level]
        payload = {
            "legacy_system": "assistant_memory_v1",
            "legacy_record": record.model_dump(mode="json"),
            "migration_version": "memory-v2-legacy-import@1",
        }
        return self.observation_store.append(
            ObservationAppendRequest(
                space=space,
                visibility_scope=VisibilityScope(kind=record.scope, scope_id=record.scope_id),
                event_type="imported_legacy_memory",
                occurred_at=_parse_timestamp(record.updated_at),
                provenance=ObservationProvenance(
                    source_type="migration",
                    source_id=f"v1-memory:{record.id}"[:240],
                    trust_level=trust,
                ),
                idempotency_key=f"legacy-memory:{digest}",
                observation_id=f"obs:legacy:{digest[:40]}",
                payload=payload,
            )
        )

    def import_records(
        self,
        *,
        principal_id: str,
        records: list[MemoryRecord],
    ) -> tuple[Observation, ...]:
        imported = []
        for record in records:
            observation = self.import_record(principal_id=principal_id, record=record)
            if observation is not None:
                imported.append(observation)
        return tuple(imported)


def legacy_seed_projector(observations: tuple[Observation, ...]) -> tuple[GraphAssertion, ...]:
    assertions: list[GraphAssertion] = []
    for observation in observations:
        if observation.event_type != "imported_legacy_memory":
            continue
        legacy = observation.payload.get("legacy_record")
        if not isinstance(legacy, dict):
            continue
        record_id = str(legacy.get("id", ""))
        content = str(legacy.get("content", "")).strip()
        kind = str(legacy.get("kind", "semantic_fact"))
        if not record_id or not content:
            continue
        revision = int(legacy.get("revision", 1))
        digest = _legacy_digest(observation.space, record_id, revision)
        domain = _KIND_DOMAIN_MAP.get(kind, "fact")
        assertions.append(
            GraphAssertion(
                assertion_id=f"legacy-seed:{digest[:48]}",
                space=observation.space,
                visibility_scopes=(observation.visibility_scope,),
                subject=GraphEntityRef(
                    entity_id=observation.space.principal_id,
                    entity_type="profile",
                ),
                predicate=f"legacy_{kind}",
                object=GraphValue(kind="literal", literal=content),
                domain=domain,
                assertion_type="seeded",
                confidence=float(legacy.get("confidence", 1.0)),
                valid_from=observation.occurred_at,
                evidence_observation_ids=(observation.observation_id,),
                derivation_version="memory-v2-legacy-seed@1",
                status="active",
            )
        )
    return tuple(sorted(assertions, key=lambda item: item.assertion_id))


def compare_shadow_retrieval(
    *,
    space: MemorySpaceKey,
    v1_contents: list[str],
    v2_result: RetrievalResult,
    observation_watermark: int,
    graph_revision: int,
    similarity_threshold: float = 0.5,
    required_recall: float = 0.8,
) -> ShadowRetrievalQualityReport:
    if not 0.0 <= similarity_threshold <= 1.0:
        raise ValueError("similarity_threshold must be between 0 and 1")
    if not 0.0 <= required_recall <= 1.0:
        raise ValueError("required_recall must be between 0 and 1")
    v2_contents = [candidate.content for candidate in v2_result.candidates]
    best_scores = [
        max((_jaccard(content, candidate) for candidate in v2_contents), default=0.0)
        for content in v1_contents
    ]
    matched = sum(score >= similarity_threshold for score in best_scores)
    recall = matched / len(v1_contents) if v1_contents else 1.0
    matched_v2 = sum(
        max((_jaccard(content, reference) for reference in v1_contents), default=0.0)
        >= similarity_threshold
        for content in v2_contents
    )
    precision = matched_v2 / len(v2_contents) if v2_contents else (1.0 if not v1_contents else 0.0)
    mean_best = sum(best_scores) / len(best_scores) if best_scores else 1.0
    return ShadowRetrievalQualityReport(
        evaluation_id=f"shadow-eval:{uuid4()}",
        space=space,
        observation_watermark=observation_watermark,
        graph_revision=graph_revision,
        v1_result_count=len(v1_contents),
        v2_result_count=len(v2_contents),
        matched_v1_count=matched,
        recall=recall,
        precision=precision,
        mean_best_similarity=mean_best,
        similarity_threshold=similarity_threshold,
        passed=recall >= required_recall,
    )


class PostgresMemoryV2ShadowEvaluationStore:
    def __init__(
        self,
        database: PostgresDatabase | None = None,
        *,
        graph_store: PostgresMemoryV2GraphStore | None = None,
        observation_store: PostgresMemoryV2ObservationStore | None = None,
    ) -> None:
        self.database = database or default_database()
        self.graph_store = graph_store or PostgresMemoryV2GraphStore(self.database)
        self.observation_store = observation_store or PostgresMemoryV2ObservationStore(self.database)

    def record(self, report: ShadowRetrievalQualityReport) -> ShadowRetrievalQualityReport:
        if report.observation_watermark > self.observation_store.watermark(report.space):
            raise ValueError("shadow report observation watermark exceeds authoritative observation store")
        if report.graph_revision > self.graph_store.state(report.space).graph_revision:
            raise ValueError("shadow report graph revision exceeds persisted graph state")
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO omnix_memory_v2_shadow_evaluations (
                    evaluation_id, principal_id, owner_type, owner_id,
                    observation_watermark, graph_revision,
                    v1_result_count, v2_result_count, matched_v1_count,
                    recall, precision, mean_best_similarity,
                    similarity_threshold, passed
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                """,
                (
                    report.evaluation_id,
                    *_space_values(report.space),
                    report.observation_watermark,
                    report.graph_revision,
                    report.v1_result_count,
                    report.v2_result_count,
                    report.matched_v1_count,
                    report.recall,
                    report.precision,
                    report.mean_best_similarity,
                    report.similarity_threshold,
                    report.passed,
                ),
            )
        return report

    def latest(self, space: MemorySpaceKey) -> ShadowRetrievalQualityReport | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT evaluation_id, observation_watermark, graph_revision,
                       v1_result_count, v2_result_count, matched_v1_count,
                       recall, precision, mean_best_similarity,
                       similarity_threshold, passed
                  FROM omnix_memory_v2_shadow_evaluations
                 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s
                 ORDER BY created_at DESC, evaluation_id DESC
                 LIMIT 1
                """,
                _space_values(space),
            ).fetchone()
        if row is None:
            return None
        return ShadowRetrievalQualityReport(
            evaluation_id=str(row[0]),
            space=space,
            observation_watermark=int(row[1]),
            graph_revision=int(row[2]),
            v1_result_count=int(row[3]),
            v2_result_count=int(row[4]),
            matched_v1_count=int(row[5]),
            recall=float(row[6]),
            precision=float(row[7]),
            mean_best_similarity=float(row[8]),
            similarity_threshold=float(row[9]),
            passed=bool(row[10]),
        )
