from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.assistant_memory_v2 import (
    Episode,
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemorySpaceKey,
    RelationshipMetric,
    RelationshipState,
    RetrievalQuery,
    VisibilityScope,
)
from app.assistant_memory_v2.retrieval import UnifiedMemoryV2Retriever

SPACE = MemorySpaceKey(principal_id="profile:alice", owner_type="character", owner_id="sofia")
GLOBAL = VisibilityScope(kind="global", scope_id="global")
PROJECT = VisibilityScope(kind="project", scope_id="project:omnix")
NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


class FakeObservationStore:
    def __init__(self, *, watermark: int = 7, inactive: set[str] | None = None) -> None:
        self._watermark = watermark
        self.inactive = inactive or set()

    def watermark(self, space):
        assert space == SPACE
        return self._watermark

    def disposition(self, observation_id):
        if observation_id in self.inactive:
            return SimpleNamespace(state="revoked")
        return None


class FakeGraphStore:
    def __init__(self, assertions=()) -> None:
        self.assertions = list(assertions)

    def state(self, space):
        assert space == SPACE
        return SimpleNamespace(graph_revision=4)

    def list_assertions(self, space, *, statuses=(), domains=(), as_of=None):
        assert space == SPACE
        result = []
        for item in self.assertions:
            if statuses and item.status not in statuses:
                continue
            if domains and item.domain not in domains:
                continue
            if as_of is not None:
                if item.valid_from is not None and item.valid_from > as_of:
                    continue
                if item.valid_until is not None and item.valid_until <= as_of:
                    continue
            result.append(item)
        return result


class FakeEpisodeStore:
    def __init__(self, episodes=()) -> None:
        self.episodes = list(episodes)

    def list(self, space, *, limit=100):
        assert space == SPACE
        return self.episodes[:limit]


class FakeRelationshipStore:
    def __init__(self, relationships=()) -> None:
        self.relationships = list(relationships)

    def list(self, space, *, status="active", limit=100):
        assert space == SPACE
        items = self.relationships
        if status is not None:
            items = [item for item in items if item.status == status]
        return items[:limit]


def _assertion(
    assertion_id: str,
    value: str,
    *,
    scope: VisibilityScope = GLOBAL,
    evidence: tuple[str, ...] = ("obs:fact",),
    confidence: float = 0.9,
    valid_from: datetime | None = NOW - timedelta(days=1),
):
    return GraphAssertion(
        assertion_id=assertion_id,
        space=SPACE,
        visibility_scopes=(scope,),
        subject=GraphEntityRef(entity_id="user:alice", entity_type="user"),
        predicate="favorite_game",
        object=GraphValue(kind="literal", literal=value),
        domain="preference",
        confidence=confidence,
        valid_from=valid_from,
        evidence_observation_ids=evidence,
        derivation_version="test@1",
    )


def _episode(summary: str, *, evidence: tuple[str, ...] = ("obs:episode",)):
    return Episode(
        episode_id="episode:1",
        space=SPACE,
        visibility_scopes=(GLOBAL,),
        title="Game discussion",
        summary=summary,
        started_at=NOW - timedelta(days=10),
        observation_ids=evidence,
        importance=0.8,
        derivation_version="test@1",
    )


def _relationship(*, evidence: tuple[str, ...] = ("obs:relationship",)):
    return RelationshipState(
        relationship_id="relationship:1",
        space=SPACE,
        subject=GraphEntityRef(entity_id="sofia", entity_type="character"),
        counterpart=GraphEntityRef(entity_id="user:alice", entity_type="user"),
        metrics=(
            RelationshipMetric(
                name="trust",
                value=0.92,
                confidence=0.9,
                evidence_observation_ids=evidence,
            ),
        ),
        prompt_interpretation="Sofia has established trust with Alice and can use familiar phrasing.",
        evidence_observation_ids=evidence,
        derivation_version="test@1",
    )


def _query(**updates):
    data = {
        "query_id": "query:1",
        "space": SPACE,
        "visible_scopes": (GLOBAL,),
        "text": "favorite game cyberpunk",
        "authority": "final",
        "as_of": NOW,
        "top_k": 5,
        "token_budget": 600,
        "deadline_ms": 1000.0,
    }
    data.update(updates)
    return RetrievalQuery(**data)


def _retriever(*, assertions=(), episodes=(), relationships=(), inactive=None):
    return UnifiedMemoryV2Retriever(
        graph_store=FakeGraphStore(assertions),
        observation_store=FakeObservationStore(inactive=inactive),
        episode_store=FakeEpisodeStore(episodes),
        relationship_store=FakeRelationshipStore(relationships),
        index_graph_revision_provider=lambda _space: 3,
    )


def test_retrieval_ranks_relevant_graph_fact_and_returns_watermarks() -> None:
    relevant = _assertion("assert:cyberpunk", "Cyberpunk 2077")
    unrelated = _assertion("assert:coffee", "espresso")
    result = _retriever(assertions=(unrelated, relevant)).retrieve(_query())

    assert [item.ref_id for item in result.candidates][:2] == ["assert:cyberpunk", "assert:coffee"]
    assert result.candidates[0].scores.semantic > result.candidates[1].scores.semantic
    assert result.observation_watermark == 7
    assert result.graph_revision == 4
    assert result.index_graph_revision == 3


def test_visibility_scope_and_domain_filters_fail_closed() -> None:
    hidden = _assertion("assert:hidden", "Cyberpunk 2077", scope=PROJECT)
    visible = _assertion("assert:visible", "Cyberpunk 2077")
    result = _retriever(assertions=(hidden, visible)).retrieve(
        _query(domains=("preference",))
    )

    assert [item.ref_id for item in result.candidates] == ["assert:visible"]
    no_episode = _retriever(episodes=(_episode("Cyberpunk was discussed."),)).retrieve(
        _query(domains=("preference",))
    )
    assert no_episode.candidates == ()


def test_revoked_evidence_removes_derived_items_from_prompt_retrieval() -> None:
    assertion = _assertion("assert:revoked", "Cyberpunk 2077", evidence=("obs:revoked",))
    episode = _episode("Cyberpunk was discussed.", evidence=("obs:revoked",))
    relationship = _relationship(evidence=("obs:revoked",))
    result = _retriever(
        assertions=(assertion,),
        episodes=(episode,),
        relationships=(relationship,),
        inactive={"obs:revoked"},
    ).retrieve(_query())

    assert result.candidates == ()
    assert result.dynamic_context == ()


def test_relationship_prompt_content_uses_interpretation_not_raw_metric_precision() -> None:
    result = _retriever(relationships=(_relationship(),)).retrieve(
        _query(text="established trust familiar phrasing", domains=("relationship",))
    )

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.item_type == "relationship"
    assert candidate.content == "Sofia has established trust with Alice and can use familiar phrasing."
    assert "0.92" not in candidate.content
    assert "prompt_interpretation_only" in candidate.reasons


def test_top_k_and_token_budget_are_hard_bounds() -> None:
    assertions = tuple(
        _assertion(f"assert:{index}", f"Cyberpunk preference {index}") for index in range(8)
    )
    result = _retriever(assertions=assertions).retrieve(_query(top_k=3, token_budget=25))

    assert len(result.candidates) <= 3
    assert result.token_estimate <= 25
    assert result.dynamic_context == tuple(item.content for item in result.candidates)


def test_zero_deadline_returns_observable_empty_result_without_reads() -> None:
    result = _retriever(assertions=(_assertion("assert:one", "Cyberpunk"),)).retrieve(
        _query(deadline_ms=0.0)
    )

    assert result.candidates == ()
    assert result.dynamic_context == ()
    assert result.deadline_ms == 0.0
    assert result.elapsed_ms >= 0.0
    assert result.observation_watermark == 7
    assert result.graph_revision == 4


def test_partial_authority_uses_same_read_only_retrieval_contract() -> None:
    result = _retriever(assertions=(_assertion("assert:one", "Cyberpunk"),)).retrieve(
        _query(authority="partial")
    )

    assert [item.ref_id for item in result.candidates] == ["assert:one"]
