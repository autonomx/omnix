"""Shadow probes score v2 against v1 by evidence identity (WP-8.5)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.assistant_memory.v2 import (
    MemorySpaceKey,
    RetrievalCandidate,
    RetrievalResult,
    RetrievalScore,
)
from app.assistant_memory.v2.legacy_shadow import ShadowProbe, compare_shadow_probes
from app.assistant_memory.v2.shadow_runner import MemoryV2ShadowRunner, ShadowRunnerError

SPACE = MemorySpaceKey(principal_id="profile:alice", owner_type="character", owner_id="sofia")


def _candidate(content: str, *evidence: str) -> RetrievalCandidate:
    return RetrievalCandidate(
        ref_id=f"assertion:{content}",
        item_type="assertion",
        domain="preference",
        content=content,
        scores=RetrievalScore(composite=1.0),
        evidence_observation_ids=evidence,
    )


def _probe(target: str, content: str, allowed: set[str], *candidates: RetrievalCandidate) -> ShadowProbe:
    return ShadowProbe(
        target_observation_id=target,
        target_content=content,
        allowed_observation_ids=frozenset(allowed),
        result=RetrievalResult(
            query_id=f"probe:{target}",
            candidates=candidates,
            dynamic_context=(),
            observation_watermark=2,
            graph_revision=1,
            index_graph_revision=1,
            elapsed_ms=1.0,
            deadline_ms=50,
        ),
    )


def _compare(*probes: ShadowProbe):
    return compare_shadow_probes(space=SPACE, probes=list(probes), observation_watermark=2, graph_revision=1)


def test_every_probe_found_with_backed_candidates_passes() -> None:
    report = _compare(
        _probe("obs:a", "Skyrim is my favorite game", {"obs:a", "obs:b"},
               _candidate("Skyrim is my favorite game", "obs:a"), _candidate("Black coffee", "obs:b")),
        _probe("obs:b", "Black coffee", {"obs:a", "obs:b"}, _candidate("Black coffee", "obs:b")),
    )
    assert (report.recall, report.precision, report.passed) == (1.0, 1.0, True)
    assert (report.v1_result_count, report.v2_result_count, report.matched_v1_count) == (2, 3, 2)
    assert report.similarity_threshold == 1.0


def test_a_memory_found_only_by_similar_text_is_not_found() -> None:
    report = _compare(
        _probe("obs:a", "Skyrim is my favorite game", {"obs:a", "obs:other"},
               _candidate("Skyrim is my favorite game", "obs:other")),
    )
    assert report.recall == 0.0 and not report.passed
    assert report.mean_best_similarity == 1.0


def test_revoked_or_out_of_scope_evidence_fails_precision() -> None:
    report = _compare(
        _probe("obs:a", "Skyrim is my favorite game", {"obs:a"},
               _candidate("Skyrim is my favorite game", "obs:a"),
               _candidate("My locker code is on the blue card", "obs:revoked"),
               _candidate("Mixed evidence", "obs:a", "obs:session-elsewhere"),
               _candidate("No evidence at all")),
    )
    assert report.recall == 1.0
    assert report.precision == pytest.approx(1 / 4)
    assert report.passed is False


def test_a_space_with_nothing_to_serve_passes() -> None:
    report = _compare()
    assert (report.recall, report.precision, report.passed) == (1.0, 1.0, True)


def test_the_runner_refuses_after_cutover() -> None:
    stores = SimpleNamespace(shadow_store=None)
    runtime = SimpleNamespace(
        authority_store=stores, observation_store=None, graph_store=None, search_index=None,
        derived_store=None, local_retriever=None,
        current=lambda: SimpleNamespace(epoch=SimpleNamespace(authority="v2")),
    )
    runner = MemoryV2ShadowRunner(object(), runtime=runtime)
    with pytest.raises(ShadowRunnerError, match="v1 is authoritative"):
        runner.run()
