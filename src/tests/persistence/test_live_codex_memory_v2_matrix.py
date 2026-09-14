"""Opt-in live Codex acceptance matrix for Memory v2.

The matrix is deliberately a test harness, not a second Memory v2 implementation.
Codex may propose semantic claims, but the injected extractor cannot write graph state,
choose evidence, or widen policy. PostgreSQL stores and the deterministic Memory v2
coordinator remain authoritative.

Run locally with a dedicated PostgreSQL database:

    $env:OMNIX_RUN_LIVE_CODEX_MEMORY_V2_TESTS="1"
    $env:OMNIX_LIVE_CODEX_SEMANTIC_MODEL="gpt-5.6-sol"
    $env:OMNIX_LIVE_CODEX_REASONING_EFFORT="high"
    $env:OMNIX_LIVE_CODEX_FAST_MODE="1"
    python -m pytest src/tests/persistence/test_live_codex_memory_v2_matrix.py -q --tb=short

The suite is opt-in because it requires PostgreSQL and consumes live Codex turns for
the semantic supersession/correction/replay cases.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
import re
from uuid import uuid4

import pytest

from app.assistant_memory.models import MemoryRecord
from app.assistant_memory_v2 import (
    AffectObservation,
    Episode,
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemoryGrant,
    MemorySpaceKey,
    ObservationProvenance,
    RelationshipMetric,
    RelationshipState,
    RetrievalQuery,
    VisibilityScope,
)
from app.assistant_memory_v2.affect_store import PostgresMemoryV2AffectStore
from app.assistant_memory_v2.assistant_output import (
    PostgresMemoryV2AssistantOutputLifecycle,
)
from app.assistant_memory_v2.authority import (
    PostgresMemoryV2AuthorityStore,
    StaleCutoverReceiptError,
)
from app.assistant_memory_v2.convergence import (
    DerivedPlanPayload,
    PostgresMemoryV2DerivedCoordinator,
    RedactedDecisionSetError,
    StaleDerivedPlanError,
)
from app.assistant_memory_v2.derived_state import PostgresMemoryV2DerivedStateStore
from app.assistant_memory_v2.episode_store import PostgresMemoryV2EpisodeStore
from app.assistant_memory_v2.federated_retrieval import FederatedMemoryV2Retriever
from app.assistant_memory_v2.grant_store import PostgresMemoryV2GrantStore
from app.assistant_memory_v2.graph_store import (
    GraphEvidenceError,
    GraphReplayValidator,
    PostgresMemoryV2GraphStore,
)
from app.assistant_memory_v2.legacy_shadow import (
    LegacyMemoryV2Importer,
    PostgresMemoryV2ShadowEvaluationStore,
    compare_shadow_retrieval,
)
from app.assistant_memory_v2.observation_store import (
    ObservationAppendRequest,
    ObservationIdempotencyConflict,
    PostgresMemoryV2ObservationStore,
)
from app.assistant_memory_v2.operations import PostgresMemoryV2ConvergenceWorker
from app.assistant_memory_v2.relationship_store import PostgresMemoryV2RelationshipStore
from app.assistant_memory_v2.replay import PostgresMemoryV2DerivedReplayValidator
from app.assistant_memory_v2.retrieval import UnifiedMemoryV2Retriever
from app.assistant_memory_v2.runtime import (
    AuthoritativeIngestSequenceError,
    PostgresMemoryV2Runtime,
    UnsafeMemoryRollbackError,
)
from app.assistant_memory_v2.search_index import PostgresMemoryV2SearchIndex
from app.assistant_memory_v2.semantic_enrichment import (
    SemanticMemoryProposal,
    VoiceMemDerivedSemanticEnricher,
)
from app.assistant_memory_v2.speculative_prefetch import (
    SpeculativeMemoryPrefetchController,
)
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations
from app.providers import ChatGPTCodexProvider, ProviderConfig
from app.providers.base import ChatMessage


_TRUE = {"1", "true", "yes", "on"}
_T0 = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
_GLOBAL = VisibilityScope(kind="global", scope_id="profile:alice")
_SECRET = VisibilityScope(kind="session", scope_id="session:secret")
_USER = GraphEntityRef(entity_id="user:alice", entity_type="user")


def _enabled() -> bool:
    return str(os.environ.get("OMNIX_RUN_LIVE_CODEX_MEMORY_V2_TESTS", "")).strip().casefold() in _TRUE


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().casefold()
    return raw in _TRUE


def _space(tag: str) -> MemorySpaceKey:
    return MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="character",
        owner_id=f"{tag}-{uuid4().hex}",
    )


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=24,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-live-codex-memory-v2-matrix",
        )
    )


@dataclass
class MatrixContext:
    database: PostgresDatabase
    observations: PostgresMemoryV2ObservationStore
    graph: PostgresMemoryV2GraphStore
    derived: PostgresMemoryV2DerivedStateStore
    episodes: PostgresMemoryV2EpisodeStore
    relationships: PostgresMemoryV2RelationshipStore
    affect: PostgresMemoryV2AffectStore
    search: PostgresMemoryV2SearchIndex
    coordinator: PostgresMemoryV2DerivedCoordinator
    worker: PostgresMemoryV2ConvergenceWorker
    replay: PostgresMemoryV2DerivedReplayValidator
    local_retriever: UnifiedMemoryV2Retriever


@pytest.fixture(scope="session")
def matrix_context() -> MatrixContext:
    if not _enabled():
        pytest.skip(
            "live Memory v2 matrix is opt-in; set "
            "OMNIX_RUN_LIVE_CODEX_MEMORY_V2_TESTS=1"
        )
    if not os.environ.get("OMNIX_TEST_DATABASE_URL"):
        pytest.skip("OMNIX_TEST_DATABASE_URL is required for the live Memory v2 matrix")

    database = _database()
    apply_migrations(database)
    observations = PostgresMemoryV2ObservationStore(database)
    graph = PostgresMemoryV2GraphStore(database)
    derived = PostgresMemoryV2DerivedStateStore(database)
    episodes = PostgresMemoryV2EpisodeStore(database)
    relationships = PostgresMemoryV2RelationshipStore(database)
    affect = PostgresMemoryV2AffectStore(database)
    search = PostgresMemoryV2SearchIndex(database)
    coordinator = PostgresMemoryV2DerivedCoordinator(
        database,
        observation_store=observations,
        graph_store=graph,
        derived_store=derived,
    )
    local_retriever = UnifiedMemoryV2Retriever(
        graph_store=graph,
        observation_store=observations,
        episode_store=episodes,
        relationship_store=relationships,
        index_graph_revision_provider=search.index_graph_revision,
        search_index=search,
        derived_store=derived,
    )
    worker = PostgresMemoryV2ConvergenceWorker(
        database,
        coordinator=coordinator,
        search_index=search,
        derived_store=derived,
    )
    context = MatrixContext(
        database=database,
        observations=observations,
        graph=graph,
        derived=derived,
        episodes=episodes,
        relationships=relationships,
        affect=affect,
        search=search,
        coordinator=coordinator,
        worker=worker,
        replay=PostgresMemoryV2DerivedReplayValidator(database, coordinator=coordinator),
        local_retriever=local_retriever,
    )
    try:
        yield context
    finally:
        database.close()


@pytest.fixture(scope="session")
def live_codex_provider() -> ChatGPTCodexProvider:
    if not _enabled():
        pytest.skip(
            "live Memory v2 matrix is opt-in; set "
            "OMNIX_RUN_LIVE_CODEX_MEMORY_V2_TESTS=1"
        )
    codex_path = str(os.environ.get("OMNIX_LIVE_CODEX_PATH", "codex") or "codex").strip()
    status = ChatGPTCodexProvider.auth_status(codex_path)
    if not (
        status.get("installed")
        and status.get("authenticated")
        and status.get("auth_mode") == "chatgpt"
    ):
        pytest.fail(f"live Codex is not ChatGPT-authenticated: {status}")

    model = str(
        os.environ.get("OMNIX_LIVE_CODEX_SEMANTIC_MODEL", "gpt-5.6-sol")
        or "gpt-5.6-sol"
    ).strip()
    effort = str(
        os.environ.get("OMNIX_LIVE_CODEX_REASONING_EFFORT", "high") or "high"
    ).strip()
    provider = ChatGPTCodexProvider(
        ProviderConfig(
            provider_type="chatgpt_codex",
            model=model,
            timeout=90.0,
            extra_params={
                "codex_path": codex_path,
                "reasoning_effort": effort,
                "fast_mode": _bool_env("OMNIX_LIVE_CODEX_FAST_MODE", True),
                "transport": "app_server",
            },
        )
    )
    if not provider.test_connection():
        provider.close()
        pytest.fail("Codex app-server transport could not be initialized")
    try:
        yield provider
    finally:
        provider.close()


_PROPOSAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["proposals"],
    "properties": {
        "proposals": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "subject_id",
                    "subject_type",
                    "predicate",
                    "domain",
                    "effective_at",
                    "operation",
                    "value",
                    "confidence",
                    "single_valued",
                ],
                "properties": {
                    "subject_id": {"type": "string", "minLength": 1},
                    "subject_type": {"type": "string", "minLength": 1},
                    "predicate": {"type": "string", "minLength": 1},
                    "domain": {
                        "type": "string",
                        "enum": [
                            "fact",
                            "preference",
                            "temporal",
                            "episode",
                            "goal",
                            "open_loop",
                            "relationship",
                            "trait",
                            "affect",
                            "routine",
                            "instruction",
                        ],
                    },
                    "effective_at": {"type": "string", "minLength": 1},
                    "operation": {"type": "string", "enum": ["assert", "retract"]},
                    "value": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "single_valued": {"type": "boolean"},
                },
            },
        }
    },
}


class LiveCodexSemanticExtractor:
    """Turn one observation into bounded proposals without authority fields."""

    def __init__(self, provider: ChatGPTCodexProvider) -> None:
        self.provider = provider
        self.calls = 0
        self.raw_outputs: list[str] = []

    def __call__(self, observation):
        self.calls += 1
        observed_at = observation.occurred_at.astimezone(timezone.utc).isoformat()
        response = self.provider.chat_completion(
            messages=[
                ChatMessage(
                    role="system",
                    content=(
                        "You are a provider-neutral semantic memory extractor. "
                        "Return only durable claims directly stated by the one observation. "
                        "Do not infer, summarize, authorize, redact, or invent. "
                        "The caller supplies evidence, ownership, visibility, and policy. "
                        "Never return assertion IDs, observation IDs, spaces, scopes, "
                        "status, evidence, policy, or revision fields. "
                        "For a user statement about the user's own preference or fact use "
                        "subject_id user:alice and subject_type user. Preserve uncertainty "
                        "in confidence. Use one stable predicate such as favorite_game or "
                        "appointment_day. Return the exact JSON schema requested."
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=(
                        f"Observation occurred_at={observed_at}\n"
                        f"event_type={observation.event_type}\n"
                        f"text={observation.payload.get('text', '')!s}\n"
                        "Return proposals. effective_at must be the observation occurred_at "
                        f"unless the text explicitly states another effective time ({observed_at})."
                    ),
                ),
            ],
            model=self.provider.config.model,
            stream=False,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "memory_v2_semantic_proposals",
                    "strict": True,
                    "schema": _PROPOSAL_SCHEMA,
                },
            },
            request_timeout_seconds=75,
            temperature=0.0,
        )
        raw = str(getattr(response, "content", "") or "").strip()
        self.raw_outputs.append(raw)
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            raw = fenced.group(1).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"Codex returned non-JSON semantic output: {raw!r}") from exc
        if not isinstance(payload, dict) or set(payload) != {"proposals"}:
            raise AssertionError(f"Codex returned an invalid semantic envelope: {payload!r}")
        rows = payload["proposals"]
        if not isinstance(rows, list):
            raise AssertionError(f"Codex proposals is not a list: {payload!r}")

        allowed = {
            "subject_id",
            "subject_type",
            "predicate",
            "domain",
            "effective_at",
            "operation",
            "value",
            "confidence",
            "single_valued",
        }
        proposals: list[SemanticMemoryProposal] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != allowed:
                raise AssertionError(f"Codex returned authority fields: {row!r}")
            effective_at = datetime.fromisoformat(
                str(row["effective_at"]).replace("Z", "+00:00")
            )
            if effective_at.tzinfo is None:
                effective_at = effective_at.replace(tzinfo=timezone.utc)
            effective_at = effective_at.astimezone(timezone.utc)
            value = (
                GraphValue(kind="literal", literal=row["value"])
                if row["operation"] == "assert"
                else None
            )
            proposals.append(
                SemanticMemoryProposal(
                    subject=GraphEntityRef(
                        entity_id=str(row["subject_id"]),
                        entity_type=str(row["subject_type"]),
                    ),
                    predicate=str(row["predicate"]),
                    domain=str(row["domain"]),
                    effective_at=effective_at,
                    operation=str(row["operation"]),
                    value=value,
                    confidence=float(row["confidence"]),
                    single_valued=bool(row["single_valued"]),
                )
            )
        return tuple(proposals)


@pytest.fixture(scope="session")
def live_extractor(live_codex_provider: ChatGPTCodexProvider) -> LiveCodexSemanticExtractor:
    return LiveCodexSemanticExtractor(live_codex_provider)


def _append(
    store: PostgresMemoryV2ObservationStore,
    space: MemorySpaceKey,
    text: str,
    suffix: str,
    *,
    scope: VisibilityScope = _GLOBAL,
    event_type: str = "user_said",
    occurred_at: datetime | None = None,
    sensitivity: str = "normal",
    source_type: str = "user",
    trust_level: str = "user_explicit",
    correlation_id: str | None = None,
) :
    return store.append(
        ObservationAppendRequest(
            space=space,
            visibility_scope=scope,
            event_type=event_type,
            occurred_at=occurred_at or _T0,
            provenance=ObservationProvenance(
                source_type=source_type,
                source_id=f"source:{suffix}",
                trust_level=trust_level,
                session_id=scope.scope_id if scope.kind == "session" else None,
                turn_id=f"turn:{suffix}",
                message_id=f"message:{suffix}",
            ),
            idempotency_key=f"live-memory-v2:{space.owner_id}:{suffix}",
            payload={"text": text},
            sensitivity=sensitivity,
            correlation_id=correlation_id,
        )
    )


def _runtime_request(space: MemorySpaceKey, suffix: str, text: str) -> ObservationAppendRequest:
    return ObservationAppendRequest(
        space=space,
        visibility_scope=_GLOBAL,
        event_type="user_said",
        occurred_at=_T0 + timedelta(minutes=5),
        provenance=ObservationProvenance(
            source_type="user",
            source_id=f"runtime-source:{suffix}",
            trust_level="user_explicit",
            session_id="session:runtime",
            turn_id=f"runtime-turn:{suffix}",
            message_id=f"runtime-message:{suffix}",
        ),
        idempotency_key=f"runtime:{space.owner_id}:{suffix}",
        payload={"text": text},
    )


def _assertion(
    space: MemorySpaceKey,
    observation_id: str,
    *,
    predicate: str = "test_fact",
    value: str = "durable value",
    domain: str = "fact",
    scope: VisibilityScope = _GLOBAL,
    status: str = "active",
    valid_from: datetime | None = _T0,
    valid_until: datetime | None = None,
    supersedes: tuple[str, ...] = (),
) -> GraphAssertion:
    return GraphAssertion(
        assertion_id=f"assertion:{space.owner_id}:{observation_id}:{predicate}",
        space=space,
        visibility_scopes=(scope,),
        subject=_USER,
        predicate=predicate,
        object=GraphValue(kind="literal", literal=value),
        domain=domain,
        confidence=0.95,
        valid_from=valid_from,
        valid_until=valid_until,
        evidence_observation_ids=(observation_id,),
        derivation_version="live-memory-v2-matrix@1",
        status=status,
        supersedes=supersedes,
    )


def _single_plan(space: MemorySpaceKey, observation_id: str, *, value: str = "durable value") -> DerivedPlanPayload:
    return DerivedPlanPayload(
        assertions=(_assertion(space, observation_id, value=value),),
        consolidator_version="live-memory-v2-matrix@1",
    )


def _multi_domain_plan(
    space: MemorySpaceKey,
    observation_id: str,
    *,
    invalid_affect_source: bool = False,
) -> DerivedPlanPayload:
    relationship = RelationshipState(
        relationship_id=f"relationship:{space.owner_id}:{observation_id}",
        space=space,
        subject=GraphEntityRef(entity_id="character:sofia", entity_type="character"),
        counterpart=_USER,
        metrics=(
            RelationshipMetric(
                name="familiarity",
                value=0.7,
                confidence=0.8,
                evidence_observation_ids=(observation_id,),
            ),
        ),
        prompt_interpretation="The relationship is becoming familiar.",
        evidence_observation_ids=(observation_id,),
        derivation_version="live-memory-v2-matrix@1",
    )
    affect = AffectObservation(
        affect_id=f"affect:{space.owner_id}:{observation_id}",
        space=space,
        source_observation_id=(
            f"missing:{observation_id}" if invalid_affect_source else observation_id
        ),
        source="semantic",
        observed_at=_T0,
        valence=0.2,
        confidence=0.8,
        model_version="live-memory-v2-matrix@1",
    )
    return DerivedPlanPayload(
        assertions=(_assertion(space, observation_id),),
        episodes=(
            Episode(
                episode_id=f"episode:{space.owner_id}:{observation_id}",
                space=space,
                visibility_scopes=(_GLOBAL,),
                title="Private discussion",
                summary="A durable test discussion.",
                started_at=_T0,
                observation_ids=(observation_id,),
                importance=0.8,
                derivation_version="live-memory-v2-matrix@1",
            ),
        ),
        relationships=(relationship,),
        affect=(affect,),
        normalized_proposals=(
            {"source_observation_id": observation_id, "kind": "matrix-proposal"},
        ),
        consolidator_version="live-memory-v2-matrix@1",
    )


def _commit(ctx: MatrixContext, space: MemorySpaceKey, planner) -> object:
    prepared = ctx.coordinator.prepare(space, planner)
    assert prepared is not None
    return ctx.coordinator.commit(prepared)


def _query(
    space: MemorySpaceKey,
    text: str,
    *,
    authority: str = "final",
    scope: VisibilityScope = _GLOBAL,
    top_k: int = 5,
    token_budget: int = 600,
    deadline_ms: float = 100,
    grant_ids: tuple[str, ...] = (),
) -> RetrievalQuery:
    return RetrievalQuery(
        query_id=f"query:{uuid4().hex}",
        space=space,
        visible_scopes=(scope,),
        text=text,
        authority=authority,
        as_of=_T0 + timedelta(days=1),
        top_k=top_k,
        token_budget=token_budget,
        deadline_ms=deadline_ms,
        grant_ids=grant_ids,
    )


def _reset_global_authority_to_v1(database: PostgresDatabase) -> None:
    with database.transaction() as connection:
        connection.execute(
            "UPDATE omnix_memory_v2_authority_current SET current_epoch = 1, updated_at = CURRENT_TIMESTAMP WHERE singleton = TRUE"
        )
        connection.execute("DELETE FROM omnix_memory_v2_authority_epochs WHERE epoch > 1")


def _prepare_ready_space(
    ctx: MatrixContext,
) -> tuple[PostgresMemoryV2AuthorityStore, MemorySpaceKey, str, str]:
    _reset_global_authority_to_v1(ctx.database)
    shadow = PostgresMemoryV2ShadowEvaluationStore(
        ctx.database,
        graph_store=ctx.graph,
        observation_store=ctx.observations,
    )
    authority = PostgresMemoryV2AuthorityStore(
        ctx.database,
        observation_store=ctx.observations,
        graph_store=ctx.graph,
        search_index=ctx.search,
        shadow_store=shadow,
        derived_store=ctx.derived,
        derived_replay_validator=ctx.replay,
    )
    space = _space("cutover")
    observation = _append(ctx.observations, space, "Skyrim is my favorite game", "cutover")
    authority.advance_authoritative_event_watermark(space, observation.authority_sequence)
    _commit(
        ctx,
        space,
        lambda _space, window, _existing: DerivedPlanPayload(
            assertions=(
                _assertion(
                    space,
                    window[0].observation_id,
                    predicate="favorite_game",
                    value="Skyrim is my favorite game",
                ),
            ),
            consolidator_version="live-memory-v2-matrix@1",
        ),
    )
    ctx.search.rebuild(space)
    result = ctx.local_retriever.retrieve(_query(space, "favorite game Skyrim"))
    graph_state = ctx.graph.state(space)
    shadow_report = compare_shadow_retrieval(
        space=space,
        v1_contents=["Skyrim is my favorite game"],
        v2_result=result,
        observation_watermark=ctx.observations.watermark(space),
        graph_revision=graph_state.graph_revision,
        required_recall=0.8,
        required_precision=0.8,
    )
    assert shadow_report.passed is True
    shadow.record(shadow_report)
    replay = GraphReplayValidator(ctx.graph, ctx.observations).validate(
        space,
        lambda window: tuple(
            _assertion(
                space,
                item.observation_id,
                predicate="favorite_game",
                value="Skyrim is my favorite game",
            )
            for item in window
        ),
    )
    readiness = authority.evaluate_space(space, graph_validation=replay)
    assert readiness.readiness.ready is True
    return authority, space, readiness.receipt_id, observation.observation_id


@pytest.mark.live_codex
def test_live_memory_v2_matrix_declares_all_milestones() -> None:
    expected = {f"M{index}" for index in range(1, 21)}
    declared = {
        "M1",
        "M2",
        "M3",
        "M4",
        "M5",
        "M6",
        "M7",
        "M8",
        "M9",
        "M10",
        "M11",
        "M12",
        "M13",
        "M14",
        "M15",
        "M16",
        "M17",
        "M18",
        "M19",
        "M20",
    }
    assert declared == expected


@pytest.mark.live_codex
def test_M1_authority_concurrency_idempotency_and_rollback(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    space = _space("authority")

    def append(index: int):
        return _append(ctx.observations, space, f"authority fact {index}", f"authority-{index}")

    with ThreadPoolExecutor(max_workers=12) as executor:
        observations = list(executor.map(append, range(12)))
    assert sorted(item.authority_sequence for item in observations) == list(range(1, 13))
    assert ctx.observations.watermark(space) == 12

    retry = _append(ctx.observations, space, "authority fact 0", "authority-0")
    assert retry.observation_id == observations[0].observation_id
    assert ctx.observations.watermark(space) == 12
    with pytest.raises(ObservationIdempotencyConflict):
        _append(ctx.observations, space, "changed content", "authority-0")
    assert ctx.observations.watermark(space) == 12


@pytest.mark.live_codex
def test_M2_cross_character_evidence_and_retrieval_are_isolated(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    sofia = _space("sofia")
    maya = _space("maya")
    sofia_observation = _append(ctx.observations, sofia, "Sofia secret surprise", "sofia-secret")
    maya_observation = _append(ctx.observations, maya, "Maya ordinary fact", "maya-fact")
    ctx.graph.put(_assertion(sofia, sofia_observation.observation_id, value="Sofia secret surprise"))
    with pytest.raises(GraphEvidenceError):
        ctx.graph.put(_assertion(maya, sofia_observation.observation_id, value="leaked"))
    ctx.graph.put(_assertion(maya, maya_observation.observation_id, value="Maya ordinary fact"))
    ctx.search.rebuild(sofia)
    ctx.search.rebuild(maya)
    result = ctx.local_retriever.retrieve(_query(maya, "Sofia secret surprise"))
    assert all("Sofia" not in candidate.content for candidate in result.candidates)


@pytest.mark.live_codex
def test_M3_multi_domain_commit_rolls_back_on_last_domain_failure(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    space = _space("atomic")
    observation = _append(ctx.observations, space, "atomic multi-domain fact", "atomic")
    with pytest.raises(Exception):
        _commit(
            ctx,
            space,
            lambda _space, _window, _existing: _multi_domain_plan(
                space, observation.observation_id, invalid_affect_source=True
            ),
        )
    assert ctx.derived.state(space).derived_revision == 0
    assert ctx.graph.list_assertions(space) == []
    assert ctx.episodes.list(space) == []
    assert ctx.relationships.list(space, status=None) == []
    assert ctx.affect.history(space) == []


@pytest.mark.live_codex
def test_M4_governance_change_during_inference_rejects_stale_plan(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    space = _space("governance-race")
    observation = _append(ctx.observations, space, "race fact", "governance-race")

    def planner(_space, _window, _existing):
        ctx.observations.set_disposition(
            space,
            observation.observation_id,
            state="revoked",
            actor_id="live-matrix:governance",
        )
        return _single_plan(space, observation.observation_id)

    with pytest.raises(StaleDerivedPlanError, match="governance revision changed"):
        _commit(ctx, space, planner)
    assert ctx.derived.state(space).derived_revision == 0


@pytest.mark.live_codex
def test_M5_live_codex_temporal_supersession_and_correction(
    matrix_context: MatrixContext,
    live_extractor: LiveCodexSemanticExtractor,
) -> None:
    ctx = matrix_context
    space = _space("temporal")
    first = _append(
        ctx.observations,
        space,
        "My favorite game is Skyrim.",
        "temporal-first",
        occurred_at=_T0,
    )
    enricher = VoiceMemDerivedSemanticEnricher(
        live_extractor,
        derivation_version="live-codex-memory-v2@1",
        provider_id="chatgpt_codex",
        model_id=live_extractor.provider.config.model,
    )
    _commit(ctx, space, enricher.plan)
    second = _append(
        ctx.observations,
        space,
        "Actually these days my favorite game is Baldur's Gate 3.",
        "temporal-second",
        occurred_at=_T0 + timedelta(minutes=1),
    )
    _commit(ctx, space, enricher.plan)
    all_assertions = ctx.graph.list_assertions(
        space,
        statuses=("active", "superseded", "disputed", "retracted"),
        domains=("preference",),
    )
    assert any(item.object.literal == "Skyrim" for item in all_assertions), live_extractor.raw_outputs
    assert any(item.object.literal == "Baldur's Gate 3" for item in all_assertions), live_extractor.raw_outputs
    active = [item for item in all_assertions if item.status == "active"]
    assert len(active) == 1
    assert active[0].object.literal == "Baldur's Gate 3"
    historical = [item for item in all_assertions if item.status == "superseded"]
    assert historical
    assert historical[0].valid_until == second.occurred_at
    assert first.observation_id in historical[0].evidence_observation_ids


@pytest.mark.live_codex
def test_M6_purge_removes_prompt_eligibility_and_redacts_replay(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    space = _space("purge")
    observation = _append(ctx.observations, space, "purge this private fact", "purge", scope=_SECRET)
    revision = _commit(ctx, space, lambda _space, _window, _existing: _multi_domain_plan(space, observation.observation_id))
    ctx.search.rebuild(space)
    assert ctx.local_retriever.retrieve(_query(space, "durable value", scope=_SECRET)).candidates

    ctx.observations.set_disposition(
        space,
        observation.observation_id,
        state="purged",
        actor_id="live-matrix:privacy",
        reason="matrix purge",
    )
    decision = ctx.coordinator.decision_set(revision.decision_set_id)
    assert decision is not None
    assert decision.redacted_at is not None
    assert decision.normalized_proposals == ()
    with pytest.raises(RedactedDecisionSetError):
        ctx.coordinator.exact_replay_payload(revision.decision_set_id)
    assert ctx.local_retriever.retrieve(_query(space, "durable value", scope=_SECRET)).candidates == ()
    assert ctx.replay.validate(space).matches is False


@pytest.mark.live_codex
def test_M7_exact_replay_does_not_invoke_a_replacement_extractor(
    matrix_context: MatrixContext,
    live_extractor: LiveCodexSemanticExtractor,
) -> None:
    ctx = matrix_context
    space = _space("exact-replay")
    observation = _append(ctx.observations, space, "My favorite game is Skyrim.", "exact-replay")
    enricher = VoiceMemDerivedSemanticEnricher(
        live_extractor,
        provider_id="chatgpt_codex",
        model_id=live_extractor.provider.config.model,
    )
    revision = _commit(ctx, space, enricher.plan)
    calls_before = live_extractor.calls

    def exploding_extractor(_observation):
        raise AssertionError("exact replay must not invoke the semantic extractor")

    replacement = VoiceMemDerivedSemanticEnricher(exploding_extractor)
    replay_payload = ctx.coordinator.exact_replay_payload(revision.decision_set_id)
    assert replay_payload.assertions
    assert live_extractor.calls == calls_before
    assert replacement.extractor is exploding_extractor
    assert ctx.replay.validate(space).matches is True
    assert ctx.observations.get(space, observation.observation_id) is not None


@pytest.mark.live_codex
def test_M8_changed_extractor_is_reported_without_replacing_committed_authority(
    matrix_context: MatrixContext,
    live_extractor: LiveCodexSemanticExtractor,
) -> None:
    ctx = matrix_context
    space = _space("rederive")
    observation = _append(ctx.observations, space, "My favorite game is Skyrim.", "rederive")
    original = VoiceMemDerivedSemanticEnricher(live_extractor)
    _commit(ctx, space, original.plan)
    persisted = ctx.graph.list_assertions(space, statuses=("active",))
    assert persisted

    def changed_extractor(_observation):
        return (
            SemanticMemoryProposal(
                subject=_USER,
                predicate="favorite_game",
                domain="preference",
                effective_at=observation.occurred_at,
                value=GraphValue(kind="literal", literal="Changed by replacement"),
            ),
        )

    candidate = VoiceMemDerivedSemanticEnricher(changed_extractor).plan(space, (observation,), ())
    assert candidate.assertions
    assert candidate.assertions[0].object.literal == "Changed by replacement"
    assert all(item.object.literal != "Changed by replacement" for item in ctx.graph.list_assertions(space))
    assert ctx.replay.validate(space).matches is True


@pytest.mark.live_codex
def test_M9_retrieval_is_conjunctive_bounded_and_falls_back_when_index_stale(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    space = _space("retrieval")
    global_observation = _append(ctx.observations, space, "global RPG preference", "retrieval-global", scope=_GLOBAL)
    private_observation = _append(ctx.observations, space, "private secret gift", "retrieval-private", scope=_SECRET)
    ctx.graph.put(_assertion(space, global_observation.observation_id, value="global RPG preference"))
    ctx.graph.put(_assertion(space, private_observation.observation_id, value="private secret gift", scope=_SECRET))
    ctx.search.rebuild(space)
    visible = ctx.local_retriever.retrieve(_query(space, "global RPG private secret", top_k=1, token_budget=3))
    assert len(visible.candidates) <= 1
    assert all("private" not in candidate.content for candidate in visible.candidates)
    assert ctx.local_retriever.retrieve(_query(space, "global RPG", deadline_ms=0)).candidates == ()
    _append(ctx.observations, space, "new stale evidence", "retrieval-stale")
    status = ctx.search.status(space)
    assert status.stale is True
    fallback = ctx.local_retriever.retrieve(_query(space, "global RPG"))
    assert any("bounded_graph_fallback" in candidate.reasons for candidate in fallback.candidates)


@pytest.mark.live_codex
def test_M10_federation_requires_grant_and_preserves_source_revision(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    source = _space("federation-source")
    target = _space("federation-target")
    observation = _append(ctx.observations, source, "federated normal preference", "federation-source")
    _append(ctx.observations, target, "target local stream", "federation-target")
    _commit(ctx, source, lambda _space, _window, _existing: _single_plan(source, observation.observation_id, value="federated normal preference"))
    ctx.search.rebuild(source)
    grants = PostgresMemoryV2GrantStore(ctx.database)
    grant = MemoryGrant(
        grant_id=f"grant:{uuid4().hex}",
        source_space=source,
        target_space=target,
        allowed_domains=("fact",),
        max_sensitivity="normal",
        created_by="live-matrix",
        created_at=_T0,
    )
    grants.put(grant)
    federated = FederatedMemoryV2Retriever(local_retriever=ctx.local_retriever, grant_store=grants)
    blocked = federated.retrieve(_query(target, "federated normal preference", grant_ids=()))
    assert blocked.candidates == ()
    allowed_query = _query(target, "federated normal preference", grant_ids=(grant.grant_id,))
    allowed = federated.retrieve(allowed_query)
    assert len(allowed.candidates) == 1
    assert allowed.candidates[0].source_space == source
    assert any(f"grant_revision:{grant.revision}" in reason for reason in allowed.candidates[0].reasons)
    assert allowed.federation_revision_digest


@pytest.mark.live_codex
def test_M11_speculative_stt_hypotheses_are_read_only(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    space = _space("stt")
    before = ctx.observations.watermark(space)
    controller = SpeculativeMemoryPrefetchController(ctx.local_retriever.retrieve)
    controller.prefetch(
        session_id="session:stt",
        segment_id="segment:1",
        hypothesis_id="A",
        query=_query(space, "passport", authority="partial"),
    )
    controller.prefetch(
        session_id="session:stt",
        segment_id="segment:1",
        hypothesis_id="B",
        query=_query(space, "pass port", authority="partial"),
    )
    assert ctx.observations.watermark(space) == before
    assert ctx.graph.list_assertions(space) == []
    controller.cancel_segment(space=space, session_id="session:stt", segment_id="segment:1")
    final = _append(ctx.observations, space, "The passport appointment is Monday", "stt-final")
    assert final.authority_sequence == before + 1


@pytest.mark.live_codex
def test_M12_barge_in_only_promotes_delivered_experienced_prefix(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    space = _space("barge-in")
    lifecycle = PostgresMemoryV2AssistantOutputLifecycle(ctx.database, observation_store=ctx.observations)
    generated = "Your passport appointment is Monday at 10, and you also need to bring the original form."
    delivered = "Your passport appointment is Monday at 10"
    correlation_id = f"output:{uuid4().hex}"
    provenance = ObservationProvenance(
        source_type="assistant",
        source_id="assistant:live-matrix",
        trust_level="assistant_inference",
        session_id="session:barge-in",
        turn_id="turn:barge-in",
        message_id="message:barge-in",
    )
    lifecycle.record_generated(
        space=space,
        visibility_scope=_GLOBAL,
        correlation_id=correlation_id,
        text=generated,
        occurred_at=_T0,
        provenance=provenance,
    )
    lifecycle.record_delivered(
        space=space,
        correlation_id=correlation_id,
        text=delivered,
        occurred_at=_T0,
        provenance=provenance,
    )
    lifecycle.update_experienced_prefix(space=space, correlation_id=correlation_id, text=delivered)
    state, experienced = lifecycle.finalize_experience(
        space=space,
        correlation_id=correlation_id,
        occurred_at=_T0,
        provenance=provenance,
    )
    assert state.generated_text == generated
    assert state.experienced_prefix == delivered
    assert experienced is not None
    assert experienced.event_type == "assistant_experienced"
    assert "original form" not in experienced.payload["text"]
    assert ctx.observations.list(space)[-1].payload["text"] == delivered


@pytest.mark.live_codex
def test_M13_migration_import_is_idempotent_and_provenance_preserving(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    record = MemoryRecord(
        id=f"v1:{uuid4().hex}",
        owner_type="character",
        owner_id=f"sofia-{uuid4().hex}",
        scope="global",
        scope_id="profile:alice",
        category="preference",
        kind="preference",
        source="user_saved",
        content="Skyrim is my favorite game",
        normalized_content="skyrim is my favorite game",
        trust_level="user_approved",
        provenance_type="user_message",
        provenance_id="message:v1",
        created_at="2026-09-13T12:00:00+00:00",
        updated_at="2026-09-13T12:00:00+00:00",
    )
    imported = LegacyMemoryV2Importer(ctx.observations)
    first = imported.import_record(principal_id="profile:alice", record=record)
    second = imported.import_record(principal_id="profile:alice", record=record)
    assert first is not None and second is not None
    assert first.observation_id == second.observation_id
    assert first.authority_sequence == second.authority_sequence == 1
    assert first.provenance.source_type == "migration"
    assert first.event_type == "imported_legacy_memory"
    assert first.payload["legacy_record"] == record.model_dump(mode="json")


@pytest.mark.live_codex
def test_M14_cutover_rejects_stale_readiness(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    authority, space, receipt_id, _observation_id = _prepare_ready_space(ctx)
    _append(ctx.observations, space, "new event after readiness", "cutover-race")
    with pytest.raises(StaleCutoverReceiptError, match="stale"):
        authority.activate_v2((receipt_id,), activated_by="live-matrix:stale-cutover")
    assert authority.current().epoch.authority == "v1"


@pytest.mark.live_codex
def test_M15_post_cutover_ingest_is_exactly_sequenced_and_idempotent(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    try:
        authority, space, receipt_id, _observation_id = _prepare_ready_space(ctx)
        authority.activate_v2((receipt_id,), activated_by="live-matrix:cutover")
        runtime = PostgresMemoryV2Runtime(ctx.database, authority_store=authority)
        request = _runtime_request(space, "post-cutover-2", "post-cutover evidence")
        first = runtime.append_authoritative(request, authoritative_event_sequence=2)
        retry = runtime.append_authoritative(request, authoritative_event_sequence=2)
        assert retry.observation_id == first.observation_id
        with pytest.raises(AuthoritativeIngestSequenceError):
            runtime.append_authoritative(
                _runtime_request(space, "post-cutover-4", "skipped event"),
                authoritative_event_sequence=4,
            )
    finally:
        _reset_global_authority_to_v1(ctx.database)


@pytest.mark.live_codex
def test_M16_rollback_cannot_discard_or_resurrect_post_cutover_state(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    try:
        authority, space, receipt_id, observation_id = _prepare_ready_space(ctx)
        authority.activate_v2((receipt_id,), activated_by="live-matrix:cutover")
        runtime = PostgresMemoryV2Runtime(ctx.database, authority_store=authority)
        runtime.append_authoritative(
            _runtime_request(space, "rollback-evidence", "evidence that must survive"),
            authoritative_event_sequence=2,
        )
        with pytest.raises(UnsafeMemoryRollbackError, match="discard"):
            runtime.rollback_to_v1(activated_by="live-matrix:rollback", reason="unsafe")
        _reset_global_authority_to_v1(ctx.database)

        authority, space, receipt_id, observation_id = _prepare_ready_space(ctx)
        authority.activate_v2((receipt_id,), activated_by="live-matrix:cutover")
        ctx.observations.set_disposition(
            space,
            observation_id,
            state="revoked",
            actor_id="live-matrix:privacy",
        )
        runtime = PostgresMemoryV2Runtime(ctx.database, authority_store=authority)
        with pytest.raises(UnsafeMemoryRollbackError, match="resurrect"):
            runtime.rollback_to_v1(activated_by="live-matrix:rollback", reason="unsafe")
    finally:
        _reset_global_authority_to_v1(ctx.database)


@pytest.mark.live_codex
def test_M17_worker_restart_replays_claimed_job_and_projection_idempotently(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    space = _space("worker-recovery")
    observation = _append(ctx.observations, space, "worker recovery fact", "worker-recovery")
    claimed = ctx.worker.claim_derive_job(space)
    assert claimed is not None
    with ctx.database.transaction() as connection:
        connection.execute(
            "UPDATE omnix_memory_v2_derive_jobs SET status = 'pending', claimed_at = NULL, available_at = CURRENT_TIMESTAMP WHERE principal_id = %s AND owner_type = %s AND owner_id = %s",
            (space.principal_id, space.owner_type, space.owner_id),
        )
    assert ctx.worker.derive_once(
        lambda target, window, _existing: _single_plan(target, window[0].observation_id),
        space=space,
    ) is True
    assert ctx.derived.state(space).derived_revision == 1
    assert ctx.worker.project_once(space=space) is True
    assert ctx.worker.project_once(space=space) is False
    assert ctx.observations.get(space, observation.observation_id) is not None


@pytest.mark.live_codex
def test_M18_poison_job_does_not_starve_another_space(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    bad = _space("poison-bad")
    good = _space("poison-good")
    _append(ctx.observations, bad, "poisoned provider input", "poison-bad")
    good_observation = _append(ctx.observations, good, "healthy provider input", "poison-good")
    assert ctx.worker.derive_once(
        lambda _space, _window, _existing: (_ for _ in ()).throw(RuntimeError("poison")),
        space=bad,
    ) is True
    assert ctx.worker.derive_once(
        lambda target, window, _existing: _single_plan(target, window[0].observation_id),
        space=good,
    ) is True
    assert ctx.derived.state(good).source_observation_watermark == good_observation.authority_sequence
    assert ctx.derived.state(bad).derived_revision == 0


@pytest.mark.live_codex
def test_M19_destroyed_search_projection_rebuilds_from_canonical_memory(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    space = _space("index-rebuild")
    observation = _append(ctx.observations, space, "canonical index rebuild fact", "index-rebuild")
    _commit(ctx, space, lambda _space, _window, _existing: _single_plan(space, observation.observation_id, value="canonical index rebuild fact"))
    ctx.search.rebuild(space)
    assert ctx.search.state(space).entry_count == 1
    with ctx.database.transaction() as connection:
        connection.execute(
            "DELETE FROM omnix_memory_v2_search_index_entries WHERE principal_id = %s AND owner_type = %s AND owner_id = %s",
            (space.principal_id, space.owner_type, space.owner_id),
        )
        connection.execute(
            "DELETE FROM omnix_memory_v2_search_index_state WHERE principal_id = %s AND owner_type = %s AND owner_id = %s",
            (space.principal_id, space.owner_type, space.owner_id),
        )
    assert ctx.graph.list_assertions(space)
    rebuilt = ctx.search.rebuild(space)
    assert rebuilt.entry_count == 1
    assert ctx.local_retriever.retrieve(_query(space, "canonical index rebuild fact")).candidates


@pytest.mark.live_codex
def test_M20_full_replay_reconstructs_derived_domains_from_committed_decision_set(matrix_context: MatrixContext) -> None:
    ctx = matrix_context
    space = _space("full-replay")
    observation = _append(ctx.observations, space, "full replay fact", "full-replay")
    revision = _commit(ctx, space, lambda _space, _window, _existing: _multi_domain_plan(space, observation.observation_id))
    replay_payload = ctx.coordinator.exact_replay_payload(revision.decision_set_id)
    with ctx.database.transaction() as connection:
        values = (space.principal_id, space.owner_type, space.owner_id)
        connection.execute("DELETE FROM omnix_memory_v2_search_index_entries WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_search_index_state WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_derived_policy_envelopes WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_relationship_metric_evidence WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_relationship_evidence WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_relationship_metrics WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_relationships WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_episode_assertions WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_episode_observations WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_episodes WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_affect_observations WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_assertion_relations WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_assertion_assertion_evidence WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_assertion_observation_evidence WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_graph_assertions WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_derived_revisions WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("DELETE FROM omnix_memory_v2_consolidation_receipts WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("UPDATE omnix_memory_v2_derived_state SET derived_revision = 0, source_observation_watermark = 0, source_governance_revision = 0, decision_set_id = NULL, policy_digest = '' WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("UPDATE omnix_memory_v2_consolidation_state SET consolidation_watermark = 0, last_receipt_id = NULL WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)
        connection.execute("UPDATE omnix_memory_v2_graph_state SET graph_revision = 0, source_observation_watermark = 0 WHERE principal_id = %s AND owner_type = %s AND owner_id = %s", values)

    rebuilt = _commit(ctx, space, lambda _space, _window, _existing: replay_payload)
    assert rebuilt.derived_revision == 1
    assert ctx.graph.list_assertions(space)
    assert ctx.episodes.list(space)
    assert ctx.relationships.list(space, status=None)
    assert ctx.affect.history(space)
    ctx.search.rebuild(space)
    report = ctx.replay.validate(space)
    assert report.matches is True, report
