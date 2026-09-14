from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import datetime

from .contracts import (
    Episode,
    GraphAssertion,
    GraphValue,
    MemoryDomain,
    MemorySpaceKey,
    RelationshipState,
    RetrievalCandidate,
    RetrievalQuery,
    RetrievalResult,
    RetrievalScore,
    VisibilityScope,
)
from .episode_store import PostgresMemoryV2EpisodeStore
from .graph_store import PostgresMemoryV2GraphStore
from .observation_store import PostgresMemoryV2ObservationStore
from .relationship_store import PostgresMemoryV2RelationshipStore

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _lexical_similarity(query: str, content: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    content_tokens = _tokens(content)
    if not content_tokens:
        return 0.0
    return len(query_tokens & content_tokens) / len(query_tokens)


def _scope_visible(
    item_scopes: tuple[VisibilityScope, ...],
    visible_scopes: tuple[VisibilityScope, ...],
) -> bool:
    allowed = {(scope.kind, scope.scope_id) for scope in visible_scopes}
    return any((scope.kind, scope.scope_id) in allowed for scope in item_scopes)


def _object_text(value: GraphValue) -> str:
    if value.kind == "entity" and value.entity is not None:
        return value.entity.entity_id
    return str(value.literal)


def _assertion_content(item: GraphAssertion) -> str:
    return f"{item.subject.entity_id} {item.predicate.replace('_', ' ')} {_object_text(item.object)}"


def _episode_content(item: Episode) -> str:
    return f"{item.title}: {item.summary}"


def _relationship_content(item: RelationshipState) -> str:
    return item.prompt_interpretation


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _recency_score(timestamp: datetime | None, as_of: datetime) -> float:
    if timestamp is None:
        return 0.5
    age_seconds = max(0.0, (as_of - timestamp).total_seconds())
    age_days = age_seconds / 86_400.0
    return 1.0 / (1.0 + age_days / 30.0)


def _mean(values: list[float], default: float = 0.0) -> float:
    return sum(values) / len(values) if values else default


IndexRevisionProvider = Callable[[MemorySpaceKey], int]


class UnifiedMemoryV2Retriever:
    """Deterministic read-only retrieval over canonical Memory v2 derived state.

    Phase 8 intentionally uses a lexical semantic proxy. Phase 9 can inject a rebuildable
    semantic index revision provider without changing retrieval authority or contracts.
    """

    def __init__(
        self,
        *,
        graph_store: PostgresMemoryV2GraphStore,
        observation_store: PostgresMemoryV2ObservationStore,
        episode_store: PostgresMemoryV2EpisodeStore,
        relationship_store: PostgresMemoryV2RelationshipStore,
        index_graph_revision_provider: IndexRevisionProvider | None = None,
    ) -> None:
        self.graph_store = graph_store
        self.observation_store = observation_store
        self.episode_store = episode_store
        self.relationship_store = relationship_store
        self.index_graph_revision_provider = index_graph_revision_provider or (lambda _space: 0)

    @staticmethod
    def _deadline_exceeded(started: float, deadline_ms: float) -> bool:
        return (time.perf_counter() - started) * 1000.0 >= deadline_ms

    def _evidence_active(self, observation_ids: tuple[str, ...]) -> bool:
        for observation_id in observation_ids:
            disposition = self.observation_store.disposition(observation_id)
            if disposition is not None and disposition.state != "active":
                return False
        return True

    @staticmethod
    def _domain_allowed(domain: MemoryDomain, query: RetrievalQuery) -> bool:
        return not query.domains or domain in query.domains

    def _assertion_candidate(
        self,
        item: GraphAssertion,
        query: RetrievalQuery,
    ) -> RetrievalCandidate | None:
        if item.status != "active" or not self._domain_allowed(item.domain, query):
            return None
        if not _scope_visible(item.visibility_scopes, query.visible_scopes):
            return None
        if not self._evidence_active(item.evidence_observation_ids):
            return None
        content = _assertion_content(item)
        semantic = _lexical_similarity(query.text, content)
        temporal = 1.0
        recency = _recency_score(item.valid_from, query.as_of)
        graph = 1.0
        composite = (
            0.42 * semantic
            + 0.18 * graph
            + 0.14 * temporal
            + 0.14 * item.confidence
            + 0.12 * recency
        )
        reasons = ["active_graph_assertion", "evidence_active", "visibility_match"]
        if semantic > 0:
            reasons.append("query_term_match")
        return RetrievalCandidate(
            ref_id=item.assertion_id,
            item_type="assertion",
            domain=item.domain,
            content=content,
            scores=RetrievalScore(
                semantic=semantic,
                graph=graph,
                temporal=temporal,
                confidence=item.confidence,
                recency=recency,
                composite=composite,
            ),
            reasons=tuple(reasons),
            evidence_observation_ids=item.evidence_observation_ids,
        )

    def _episode_candidate(self, item: Episode, query: RetrievalQuery) -> RetrievalCandidate | None:
        if not self._domain_allowed("episode", query):
            return None
        if not _scope_visible(item.visibility_scopes, query.visible_scopes):
            return None
        if item.started_at > query.as_of:
            return None
        if not self._evidence_active(item.observation_ids):
            return None
        content = _episode_content(item)
        semantic = _lexical_similarity(query.text, content)
        recency = _recency_score(item.ended_at or item.started_at, query.as_of)
        episodic = item.importance
        composite = 0.50 * semantic + 0.22 * episodic + 0.16 * recency + 0.12
        reasons = ["episode_evidence_active", "visibility_match"]
        if semantic > 0:
            reasons.append("query_term_match")
        return RetrievalCandidate(
            ref_id=item.episode_id,
            item_type="episode",
            domain="episode",
            content=content,
            scores=RetrievalScore(
                semantic=semantic,
                episodic=episodic,
                importance=item.importance,
                recency=recency,
                composite=composite,
            ),
            reasons=tuple(reasons),
            evidence_observation_ids=item.observation_ids,
        )

    def _relationship_candidate(
        self,
        item: RelationshipState,
        query: RetrievalQuery,
    ) -> RetrievalCandidate | None:
        if item.status != "active" or not self._domain_allowed("relationship", query):
            return None
        evidence_ids = tuple(
            dict.fromkeys(
                (
                    *item.evidence_observation_ids,
                    *(
                        evidence
                        for metric in item.metrics
                        for evidence in metric.evidence_observation_ids
                    ),
                )
            )
        )
        if not self._evidence_active(evidence_ids):
            return None
        content = _relationship_content(item)
        semantic = _lexical_similarity(query.text, content)
        metric_strength = _mean(
            [metric.value * metric.confidence for metric in item.metrics],
            default=0.5,
        )
        confidence = _mean([metric.confidence for metric in item.metrics], default=0.5)
        composite = 0.44 * semantic + 0.34 * metric_strength + 0.16 * confidence + 0.06
        reasons = ["relationship_evidence_active", "prompt_interpretation_only"]
        if semantic > 0:
            reasons.append("query_term_match")
        return RetrievalCandidate(
            ref_id=item.relationship_id,
            item_type="relationship",
            domain="relationship",
            content=content,
            scores=RetrievalScore(
                semantic=semantic,
                relationship=metric_strength,
                confidence=confidence,
                composite=composite,
            ),
            reasons=tuple(reasons),
            evidence_observation_ids=evidence_ids,
        )

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        started = time.perf_counter()
        graph_state = self.graph_store.state(query.space)
        observation_watermark = self.observation_store.watermark(query.space)
        index_graph_revision = int(self.index_graph_revision_provider(query.space))
        if query.deadline_ms == 0 or self._deadline_exceeded(started, query.deadline_ms):
            return RetrievalResult(
                query_id=query.query_id,
                observation_watermark=observation_watermark,
                graph_revision=graph_state.graph_revision,
                index_graph_revision=index_graph_revision,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                deadline_ms=query.deadline_ms,
            )

        candidates: list[RetrievalCandidate] = []
        assertions = self.graph_store.list_assertions(
            query.space,
            statuses=("active",),
            domains=query.domains,
            as_of=query.as_of,
        )
        for item in assertions:
            if self._deadline_exceeded(started, query.deadline_ms):
                break
            candidate = self._assertion_candidate(item, query)
            if candidate is not None:
                candidates.append(candidate)

        if not self._deadline_exceeded(started, query.deadline_ms):
            for item in self.episode_store.list(query.space, limit=max(query.top_k * 8, 32)):
                if self._deadline_exceeded(started, query.deadline_ms):
                    break
                candidate = self._episode_candidate(item, query)
                if candidate is not None:
                    candidates.append(candidate)

        if not self._deadline_exceeded(started, query.deadline_ms):
            for item in self.relationship_store.list(
                query.space,
                status="active",
                limit=max(query.top_k * 4, 16),
            ):
                if self._deadline_exceeded(started, query.deadline_ms):
                    break
                candidate = self._relationship_candidate(item, query)
                if candidate is not None:
                    candidates.append(candidate)

        candidates.sort(key=lambda item: (-item.scores.composite, item.item_type, item.ref_id))
        selected: list[RetrievalCandidate] = []
        context: list[str] = []
        token_estimate = 0
        for candidate in candidates:
            if len(selected) >= query.top_k:
                break
            estimate = _estimate_tokens(candidate.content)
            if token_estimate + estimate > query.token_budget:
                continue
            selected.append(candidate)
            context.append(candidate.content)
            token_estimate += estimate

        return RetrievalResult(
            query_id=query.query_id,
            candidates=tuple(selected),
            dynamic_context=tuple(context),
            token_estimate=token_estimate,
            observation_watermark=observation_watermark,
            graph_revision=graph_state.graph_revision,
            index_graph_revision=index_graph_revision,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            deadline_ms=query.deadline_ms,
        )
