from __future__ import annotations

from collections import deque

from app.assistant_context.models import AssistantContextItem
from app.research.contracts import ResearchSource, ResearchSourceSnapshot
from app.research.executor import (
    DeepResearchExecutor,
    ResearchExecutionCheckpoint,
    detect_conflicts,
)
from app.research.jobs import DeepResearchJobInput
from app.research.planner import (
    ResearchOperation,
    ResearchPlan,
    ResearchPlannerDecision,
)
from app.research.quick_search import QuickSearchExecution
from app.research.source_store import ResearchSourceStore


class FixedPlanner:
    def __init__(self, plan: ResearchPlan) -> None:
        self.plan = plan

    def plan(self, request):
        return ResearchPlannerDecision(plan=self.plan, backend="local")


class FakeQuickSearch:
    def __init__(self, execution: QuickSearchExecution, calls: list[str]) -> None:
        self.execution = execution
        self.calls = calls

    def search(self, query: str, max_results: int) -> QuickSearchExecution:
        self.calls.append(query)
        return self.execution


def source_pair(index: int, snippet: str, *, extracted: bool = False) -> tuple[ResearchSource, ResearchSourceSnapshot]:
    source_id = f"source:{index}"
    return (
        ResearchSource(
            source_record_id=source_id,
            provider="fixture",
            original_url=f"https://example.test/{index}",
            canonical_url=f"https://example.test/{index}",
            title=f"Source {index}",
            first_seen_at="2026-07-07T00:00:00Z",
        ),
        ResearchSourceSnapshot(
            snapshot_id=f"snapshot:{index}",
            source_record_id=source_id,
            citation_label="S1",
            query_id=f"query:{index}",
            rank=1,
            snippet=snippet,
            retrieved_at="2026-07-07T00:00:01Z",
            extraction_status="completed" if extracted else "not_requested",
            content_hash=f"hash-{index}" if extracted else None,
        ),
    )


def execution_for(*pairs: tuple[ResearchSource, ResearchSourceSnapshot]) -> QuickSearchExecution:
    return QuickSearchExecution(
        items=[
            AssistantContextItem(
                source_id="web_search",
                title=source.title,
                content=snapshot.snippet,
                url=source.original_url,
            )
            for source, snapshot in pairs
        ],
        sources=[source for source, _ in pairs],
        snapshots=[snapshot for _, snapshot in pairs],
    )


def test_executor_enforces_query_source_and_extract_budgets(tmp_path) -> None:
    first = source_pair(1, "The current release supports streaming.", extracted=True)
    second = source_pair(2, "The release includes source citations.")
    calls: list[str] = []
    plan = ResearchPlan(
        objective="Compare releases",
        operations=[
            ResearchOperation(operation="web_search", query="release one"),
            ResearchOperation(operation="web_search", query="release two"),
            ResearchOperation(operation="evaluate_evidence", evaluation_question="compare"),
            ResearchOperation(operation="stop", reason="enough evidence"),
        ],
    )
    queue = deque([execution_for(first, second)])
    store = ResearchSourceStore(tmp_path / "sources.json")
    executor = DeepResearchExecutor(
        planner=FixedPlanner(plan),
        source_store_factory=lambda: store,
        quick_search_factory=lambda remaining_sources, remaining_extracts: FakeQuickSearch(
            queue.popleft(), calls
        ),
    )

    result = executor.execute(
        DeepResearchJobInput(
            session_id="session:one",
            user_message_id="message:one",
            question="Compare releases",
            max_queries=1,
            max_sources=2,
            max_extracts=1,
        ),
        lambda stage, message: None,
        lambda: False,
    )

    assert calls == ["release one"]
    assert result.stop_reason == "query_budget_exhausted"
    assert result.research_status == "partial"
    assert len(result.sources) == 2
    assert result.extracted_pages == 1
    assert [snapshot.citation_label for snapshot in result.snapshots] == ["S1", "S2"]
    assert result.source_manifest_id


def test_executor_deduplicates_sources_across_queries(tmp_path) -> None:
    pair = source_pair(1, "The release supports deterministic research.")
    calls: list[str] = []
    plan = ResearchPlan(
        objective="Research release",
        operations=[
            ResearchOperation(operation="web_search", query="first"),
            ResearchOperation(operation="web_search", query="second"),
            ResearchOperation(operation="evaluate_evidence", evaluation_question="compare"),
            ResearchOperation(operation="stop", reason="done"),
        ],
    )
    queue = deque([execution_for(pair), execution_for(pair)])
    executor = DeepResearchExecutor(
        planner=FixedPlanner(plan),
        source_store_factory=lambda: ResearchSourceStore(tmp_path / "sources.json"),
        quick_search_factory=lambda remaining_sources, remaining_extracts: FakeQuickSearch(
            queue.popleft(), calls
        ),
    )

    result = executor.execute(
        DeepResearchJobInput(
            session_id="session:one",
            user_message_id="message:one",
            question="Research release",
            max_queries=2,
        ),
        lambda stage, message: None,
        lambda: False,
    )

    assert calls == ["first", "second"]
    assert len(result.sources) == 1
    assert len(result.snapshots) == 1
    assert len(result.evidence) == 1


def test_executor_resumes_after_checkpoint_without_repeating_completed_query(tmp_path) -> None:
    existing = source_pair(1, "First query evidence.")
    later = source_pair(2, "Second query evidence.")
    plan = ResearchPlan(
        objective="Resume research",
        operations=[
            ResearchOperation(operation="web_search", query="first"),
            ResearchOperation(operation="web_search", query="second"),
            ResearchOperation(operation="evaluate_evidence", evaluation_question="compare"),
            ResearchOperation(operation="stop", reason="done"),
        ],
    )
    checkpoint = ResearchExecutionCheckpoint(
        objective=plan.objective,
        plan=plan,
        planner_backend="local",
        next_operation_index=1,
        logical_queries=1,
        sources=[existing[0]],
        snapshots=[existing[1]],
    )
    calls: list[str] = []
    executor = DeepResearchExecutor(
        planner=FixedPlanner(plan),
        source_store_factory=lambda: ResearchSourceStore(tmp_path / "sources.json"),
        quick_search_factory=lambda remaining_sources, remaining_extracts: FakeQuickSearch(
            execution_for(later), calls
        ),
    )

    result = executor.execute(
        DeepResearchJobInput(
            session_id="session:one",
            user_message_id="message:one",
            question="Resume research",
            max_queries=2,
        ),
        lambda stage, message: None,
        lambda: False,
        checkpoint=checkpoint,
    )

    assert calls == ["second"]
    assert result.logical_queries == 2
    assert [source.source_record_id for source in result.sources] == ["source:1", "source:2"]


def test_conflict_detection_records_opposing_related_claims() -> None:
    positive = source_pair(1, "The release supports live audio streaming.")
    negative = source_pair(2, "The release does not support live audio streaming.")

    conflicts = detect_conflicts(
        [positive[0], negative[0]],
        [positive[1], negative[1]],
    )

    assert len(conflicts) == 1
    assert conflicts[0].status == "unresolved"
    assert conflicts[0].supporting_snapshot_ids == ["snapshot:1"]
    assert conflicts[0].contradicting_snapshot_ids == ["snapshot:2"]
