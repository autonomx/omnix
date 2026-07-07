from __future__ import annotations

import json

from app.research.contracts import ResearchEvidence, ResearchSource, ResearchSourceSnapshot
from app.research.executor import ResearchConflict, ResearchExecutionResult
from app.research.synthesis import DeepResearchSynthesizer, build_synthesis_messages


def execution_fixture() -> ResearchExecutionResult:
    source = ResearchSource(
        source_record_id="source:one",
        provider="fixture",
        original_url="https://example.test/release",
        canonical_url="https://example.test/release",
        title="Release notes",
        first_seen_at="2026-07-07T00:00:00Z",
    )
    snapshot = ResearchSourceSnapshot(
        snapshot_id="snapshot:one",
        source_record_id=source.source_record_id,
        citation_label="S1",
        query_id="query:one",
        rank=1,
        snippet="The current release supports streaming and citations.",
        retrieved_at="2026-07-07T00:00:01Z",
        extraction_status="completed",
        content_hash="hash",
        extracted_text_ref="/private/full-page.txt",
    )
    return ResearchExecutionResult(
        objective="Explain the current release",
        research_status="completed",
        planner_backend="local",
        source_manifest_id="manifest:one",
        sources=[source],
        snapshots=[snapshot],
        evidence=[
            ResearchEvidence(
                evidence_id="evidence:one",
                claim="The current release supports streaming and citations.",
                source_snapshot_ids=[snapshot.snapshot_id],
                confidence=0.8,
                notes="Extracted source available.",
            )
        ],
        conflicts=[
            ResearchConflict(
                conflict_id="conflict:one",
                summary="One secondary source disagreed about streaming latency.",
                supporting_snapshot_ids=[snapshot.snapshot_id],
                contradicting_snapshot_ids=[],
            )
        ],
        stop_reason="evidence_collected",
        logical_queries=1,
        extracted_pages=1,
    )


def test_valid_structured_synthesis_renders_snapshot_bound_citations() -> None:
    answer = {
        "sections": [
            {
                "kind": "fact",
                "text": "The current release supports streaming and citations.",
                "source_snapshot_ids": ["snapshot:one"],
            },
            {
                "kind": "inference",
                "text": "This should improve traceability.",
                "source_snapshot_ids": ["snapshot:one"],
            },
            {
                "kind": "limitation",
                "text": "Latency evidence remains disputed.",
                "source_snapshot_ids": [],
            },
        ]
    }
    synthesizer = DeepResearchSynthesizer(
        completion_fn=lambda messages, provider, model: (
            json.dumps(answer),
            {"resolved_model": "fixture-model"},
        )
    )

    result = synthesizer.synthesize(
        execution_fixture(),
        question="What changed?",
        provider_id="fixture",
        model_id="fixture-model",
    )

    assert result.backend == "provider"
    assert result.validation.valid is True
    assert "[S1]" in result.content
    assert "**Inference:**" in result.content
    assert "**Limitation:**" in result.content
    assert "## Unresolved conflicts" in result.content
    assert result.provider_metadata["resolved_model"] == "fixture-model"


def test_unknown_snapshot_id_forces_visible_deterministic_fallback() -> None:
    answer = {
        "sections": [
            {
                "kind": "fact",
                "text": "Unsupported fact.",
                "source_snapshot_ids": ["snapshot:unknown"],
            }
        ]
    }
    result = DeepResearchSynthesizer(
        completion_fn=lambda messages, provider, model: (json.dumps(answer), {})
    ).synthesize(
        execution_fixture(),
        question="What changed?",
        provider_id="fixture",
        model_id="fixture-model",
    )

    assert result.backend == "deterministic_fallback"
    assert result.validation.valid is False
    assert result.validation.unknown_snapshot_ids == ["snapshot:unknown"]
    assert "Research synthesis note" in result.content
    assert "[S1]" in result.content


def test_fact_without_evidence_and_malformed_json_fall_back() -> None:
    unsupported = json.dumps(
        {"sections": [{"kind": "fact", "text": "No support", "source_snapshot_ids": []}]}
    )
    first = DeepResearchSynthesizer(
        completion_fn=lambda messages, provider, model: (unsupported, {})
    ).synthesize(
        execution_fixture(),
        question="What changed?",
        provider_id="fixture",
        model_id="fixture-model",
    )
    second = DeepResearchSynthesizer(
        completion_fn=lambda messages, provider, model: ("not json", {})
    ).synthesize(
        execution_fixture(),
        question="What changed?",
        provider_id="fixture",
        model_id="fixture-model",
    )

    assert first.backend == "deterministic_fallback"
    assert second.backend == "deterministic_fallback"
    assert first.warnings[0].startswith("provider_synthesis_unavailable")
    assert second.warnings[0].startswith("provider_synthesis_unavailable")


def test_synthesis_prompt_uses_structured_evidence_not_extracted_page_storage() -> None:
    messages = build_synthesis_messages(execution_fixture(), question="What changed?")
    user_payload = messages[1]["content"]

    assert "snapshot:one" in user_payload
    assert "The current release supports streaming and citations." in user_payload
    assert "/private/full-page.txt" not in user_payload
    assert "extracted_text_ref" not in user_payload
    assert "tool access" in messages[0]["content"]
