from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.assistant_memory_v2 import (
    MemorySpaceKey,
    RetrievalQuery,
    RetrievalResult,
    VisibilityScope,
)
from app.assistant_memory_v2.speculative_prefetch import SpeculativeMemoryPrefetchController

SPACE = MemorySpaceKey(principal_id="profile:alice", owner_type="character", owner_id="sofia")
OTHER_SPACE = MemorySpaceKey(principal_id="profile:alice", owner_type="character", owner_id="maya")
GLOBAL = VisibilityScope(kind="global", scope_id="global")
T0 = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


class FakeRetriever:
    def __init__(self) -> None:
        self.calls: list[RetrievalQuery] = []

    def __call__(self, query: RetrievalQuery) -> RetrievalResult:
        self.calls.append(query)
        return RetrievalResult(
            query_id=query.query_id,
            observation_watermark=len(self.calls),
            graph_revision=len(self.calls),
            index_graph_revision=len(self.calls),
            elapsed_ms=1.0,
            deadline_ms=query.deadline_ms,
        )


def _query(
    text: str,
    *,
    authority: str,
    query_id: str,
    space: MemorySpaceKey = SPACE,
    as_of: datetime = T0,
    grant_ids: tuple[str, ...] = (),
) -> RetrievalQuery:
    return RetrievalQuery(
        query_id=query_id,
        space=space,
        visible_scopes=(GLOBAL,),
        text=text,
        authority=authority,
        as_of=as_of,
        top_k=5,
        token_budget=600,
        deadline_ms=50,
        grant_ids=grant_ids,
    )


def _allow_reuse(_query: RetrievalQuery, _result: RetrievalResult) -> bool:
    return True


def test_prefetch_requires_partial_authority() -> None:
    fake = FakeRetriever()
    controller = SpeculativeMemoryPrefetchController(fake)
    with pytest.raises(ValueError, match="partial retrieval authority"):
        controller.prefetch(
            session_id="s1",
            segment_id="seg1",
            hypothesis_id="h1",
            query=_query("Skyrim", authority="final", query_id="final"),
        )
    assert fake.calls == []


def test_without_reuse_guard_final_fails_closed_to_fresh_retrieval() -> None:
    fake = FakeRetriever()
    controller = SpeculativeMemoryPrefetchController(fake)
    controller.prefetch(
        session_id="s1",
        segment_id="seg1",
        hypothesis_id="h1",
        query=_query("Skyrim", authority="partial", query_id="partial"),
    )
    promotion = controller.promote_or_retrieve(
        session_id="s1",
        segment_id="seg1",
        hypothesis_id="h1",
        final_query=_query(
            "Skyrim",
            authority="final",
            query_id="final",
            as_of=T0 + timedelta(milliseconds=100),
        ),
    )
    assert promotion.reused is False
    assert len(fake.calls) == 2
    assert fake.calls[-1].authority == "final"


def test_exact_final_promotes_prefetch_when_authority_guard_passes() -> None:
    fake = FakeRetriever()
    controller = SpeculativeMemoryPrefetchController(fake, reuse_guard=_allow_reuse)
    partial = _query("Skyrim is my favorite game", authority="partial", query_id="partial")
    controller.prefetch(session_id="s1", segment_id="seg1", hypothesis_id="h1", query=partial)

    promotion = controller.promote_or_retrieve(
        session_id="s1",
        segment_id="seg1",
        hypothesis_id="h1",
        final_query=_query(
            "Skyrim is my favorite game",
            authority="final",
            query_id="final",
            as_of=T0 + timedelta(milliseconds=200),
        ),
    )

    assert promotion.reused is True
    assert promotion.source_hypothesis_id == "h1"
    assert promotion.result.query_id == "final"
    assert len(fake.calls) == 1
    assert controller.entry_count == 0


def test_reuse_guard_can_veto_compatible_cache() -> None:
    fake = FakeRetriever()
    controller = SpeculativeMemoryPrefetchController(
        fake,
        reuse_guard=lambda _query, _result: False,
    )
    controller.prefetch(
        session_id="s1",
        segment_id="seg1",
        hypothesis_id="h1",
        query=_query("Skyrim", authority="partial", query_id="partial"),
    )
    promotion = controller.promote_or_retrieve(
        session_id="s1",
        segment_id="seg1",
        hypothesis_id="h1",
        final_query=_query(
            "Skyrim",
            authority="final",
            query_id="final",
            as_of=T0 + timedelta(milliseconds=100),
        ),
    )
    assert promotion.reused is False
    assert len(fake.calls) == 2


def test_small_final_tail_can_reuse_but_correction_forces_fresh_retrieval() -> None:
    fake = FakeRetriever()
    controller = SpeculativeMemoryPrefetchController(
        fake,
        reuse_guard=_allow_reuse,
        max_tail_tokens=1,
    )
    controller.prefetch(
        session_id="s1",
        segment_id="seg1",
        hypothesis_id="h1",
        query=_query("Skyrim is my favorite game", authority="partial", query_id="partial-1"),
    )
    reused = controller.promote_or_retrieve(
        session_id="s1",
        segment_id="seg1",
        hypothesis_id="h1",
        final_query=_query(
            "Skyrim is my favorite game now",
            authority="final",
            query_id="final-1",
            as_of=T0 + timedelta(milliseconds=100),
        ),
    )
    assert reused.reused is True
    assert len(fake.calls) == 1

    controller.prefetch(
        session_id="s1",
        segment_id="seg2",
        hypothesis_id="h2",
        query=_query("Skyrim is my favorite game", authority="partial", query_id="partial-2"),
    )
    corrected = controller.promote_or_retrieve(
        session_id="s1",
        segment_id="seg2",
        hypothesis_id="h2",
        final_query=_query(
            "Cyberpunk is my favorite game",
            authority="final",
            query_id="final-2",
            as_of=T0 + timedelta(milliseconds=150),
        ),
    )
    assert corrected.reused is False
    assert len(fake.calls) == 3
    assert fake.calls[-1].authority == "final"


def test_policy_change_or_cross_space_final_cannot_reuse_partial_context() -> None:
    fake = FakeRetriever()
    controller = SpeculativeMemoryPrefetchController(fake, reuse_guard=_allow_reuse)
    controller.prefetch(
        session_id="s1",
        segment_id="seg1",
        hypothesis_id="h1",
        query=_query(
            "Skyrim favorite game",
            authority="partial",
            query_id="partial",
            grant_ids=("grant:a",),
        ),
    )
    changed_policy = controller.promote_or_retrieve(
        session_id="s1",
        segment_id="seg1",
        hypothesis_id="h1",
        final_query=_query(
            "Skyrim favorite game",
            authority="final",
            query_id="final-policy",
            as_of=T0 + timedelta(milliseconds=100),
            grant_ids=(),
        ),
    )
    assert changed_policy.reused is False
    assert len(fake.calls) == 2

    controller.prefetch(
        session_id="s2",
        segment_id="seg2",
        hypothesis_id="h2",
        query=_query("Skyrim", authority="partial", query_id="partial-space"),
    )
    cross_space = controller.promote_or_retrieve(
        session_id="s2",
        segment_id="seg2",
        hypothesis_id="h2",
        final_query=_query(
            "Skyrim",
            authority="final",
            query_id="final-space",
            space=OTHER_SPACE,
            as_of=T0 + timedelta(milliseconds=100),
        ),
    )
    assert cross_space.reused is False
    assert len(fake.calls) == 4


def test_cancel_and_expiry_force_final_retrieval() -> None:
    fake = FakeRetriever()
    now = [0.0]
    controller = SpeculativeMemoryPrefetchController(
        fake,
        reuse_guard=_allow_reuse,
        ttl_ms=1000,
        clock=lambda: now[0],
    )
    controller.prefetch(
        session_id="s1",
        segment_id="seg1",
        hypothesis_id="h1",
        query=_query("Skyrim", authority="partial", query_id="partial-1"),
    )
    assert controller.cancel(
        space=SPACE,
        session_id="s1",
        segment_id="seg1",
        hypothesis_id="h1",
    )
    cancelled = controller.promote_or_retrieve(
        session_id="s1",
        segment_id="seg1",
        hypothesis_id="h1",
        final_query=_query("Skyrim", authority="final", query_id="final-1"),
    )
    assert cancelled.reused is False
    assert len(fake.calls) == 2

    controller.prefetch(
        session_id="s1",
        segment_id="seg2",
        hypothesis_id="h2",
        query=_query("Skyrim", authority="partial", query_id="partial-2"),
    )
    now[0] = 2.0
    expired = controller.promote_or_retrieve(
        session_id="s1",
        segment_id="seg2",
        hypothesis_id="h2",
        final_query=_query(
            "Skyrim",
            authority="final",
            query_id="final-2",
            as_of=T0 + timedelta(milliseconds=200),
        ),
    )
    assert expired.reused is False
    assert len(fake.calls) == 4


def test_segment_hypothesis_bound_evicts_oldest_prefetch() -> None:
    fake = FakeRetriever()
    now = [0.0]
    controller = SpeculativeMemoryPrefetchController(
        fake,
        reuse_guard=_allow_reuse,
        max_hypotheses_per_segment=2,
        clock=lambda: now[0],
    )
    for index in range(3):
        now[0] = float(index)
        controller.prefetch(
            session_id="s1",
            segment_id="seg1",
            hypothesis_id=f"h{index}",
            query=_query(
                f"Skyrim hypothesis {index}",
                authority="partial",
                query_id=f"partial-{index}",
                as_of=T0 + timedelta(milliseconds=index),
            ),
        )
    assert controller.entry_count == 2

    promotion = controller.promote_or_retrieve(
        session_id="s1",
        segment_id="seg1",
        hypothesis_id="h0",
        final_query=_query(
            "Skyrim hypothesis 0",
            authority="final",
            query_id="final",
            as_of=T0 + timedelta(milliseconds=10),
        ),
    )
    assert promotion.reused is False
    assert len(fake.calls) == 4
    assert controller.entry_count == 0
