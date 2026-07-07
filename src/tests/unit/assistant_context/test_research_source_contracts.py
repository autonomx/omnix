from app.jobs import JobStatus, ResourceClass
from app.research import (
    RESEARCH_JOB_MODULE,
    RESEARCH_JOB_TYPE,
    RESEARCH_STAGE_IDS,
    ResearchSource,
    ResearchSourceSnapshot,
)


def test_source_identity_is_separate_from_retrieval_snapshot() -> None:
    source = ResearchSource(
        source_record_id="source:example",
        provider="brave",
        original_url="https://example.test/story",
        canonical_url="https://example.test/story",
        title="Example",
        first_seen_at="2026-07-06T00:00:00Z",
    )
    snapshot = ResearchSourceSnapshot(
        snapshot_id="snapshot:one",
        source_record_id=source.source_record_id,
        citation_label="S1",
        retrieved_at="2026-07-06T00:01:00Z",
        extractor_version="readable-v1",
        extraction_status="completed",
        content_hash="abc",
    )
    assert snapshot.source_record_id == source.source_record_id
    assert snapshot.citation_label == "S1"
    assert "content_hash" not in source.model_dump()


def test_research_uses_shared_job_contract() -> None:
    assert RESEARCH_JOB_MODULE == "assistant"
    assert RESEARCH_JOB_TYPE == "assistant.deep_research"
    assert RESEARCH_STAGE_IDS[-1] == "persisting"
    assert "cpu_network" not in {item.value for item in ResourceClass}
    assert "planning" not in {item.value for item in JobStatus}
    assert JobStatus.CANCELED.value == "canceled"
