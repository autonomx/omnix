"""Canonical contracts for assistant web research modes and provenance."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

ResearchMode = Literal["disabled", "quick", "deep"]
ResearchModeSource = Literal["turn", "conversation", "profile", "fallback"]
ResearchStatus = Literal["completed", "partial", "failed", "canceled"]
ResearchSectionKind = Literal["fact", "inference", "limitation", "recommendation"]

RESEARCH_JOB_MODULE = "assistant"
RESEARCH_JOB_TYPE = "assistant.deep_research"
RESEARCH_STAGE_IDS = (
    "planning",
    "searching",
    "extracting",
    "evaluating",
    "synthesizing",
    "persisting",
)


def normalize_research_mode(value: Any) -> ResearchMode:
    """Normalize canonical and compatibility values without enabling malformed input."""

    normalized = str(value or "").strip().lower().replace("-", "_")
    compatibility = {
        "automatic": "quick",
        "manual": "quick",
        "disabled": "disabled",
        "quick": "quick",
        "quick_search": "quick",
        "deep": "deep",
        "deep_research": "deep",
    }
    return compatibility.get(normalized, "disabled")  # type: ignore[return-value]


class ResearchModeResolution(BaseModel):
    requested_mode: ResearchMode
    effective_mode: ResearchMode
    source: ResearchModeSource
    available: bool = True
    downgraded: bool = False
    warning: str | None = None


def resolve_research_mode(
    *,
    turn_override: Any = None,
    conversation_override: Any = None,
    profile_default: Any = None,
    quick_enabled: bool = True,
    deep_enabled: bool = False,
    allow_deep_downgrade: bool = False,
) -> ResearchModeResolution:
    """Resolve mode precedence, then constrain it by runtime availability.

    Precedence is turn override, conversation override, profile default, then the
    disabled fallback. An explicitly supplied malformed value resolves to
    disabled rather than falling through to a lower-precedence value.
    """

    candidates = (
        ("turn", turn_override),
        ("conversation", conversation_override),
        ("profile", profile_default),
    )
    source: ResearchModeSource = "fallback"
    requested: ResearchMode = "disabled"
    for candidate_source, value in candidates:
        if value is None:
            continue
        source = candidate_source  # type: ignore[assignment]
        requested = normalize_research_mode(value)
        break

    if requested == "quick" and not quick_enabled:
        return ResearchModeResolution(
            requested_mode=requested,
            effective_mode="disabled",
            source=source,
            available=False,
            warning="Quick Search is unavailable; no web request was made.",
        )
    if requested == "deep" and not deep_enabled:
        if allow_deep_downgrade and quick_enabled:
            return ResearchModeResolution(
                requested_mode=requested,
                effective_mode="quick",
                source=source,
                available=False,
                downgraded=True,
                warning="Deep Research is unavailable; Quick Search was used instead.",
            )
        return ResearchModeResolution(
            requested_mode=requested,
            effective_mode="disabled",
            source=source,
            available=False,
            warning="Deep Research is unavailable; no research request was started.",
        )
    return ResearchModeResolution(
        requested_mode=requested,
        effective_mode=requested,
        source=source,
    )


class ResearchQuery(BaseModel):
    query_id: str
    text: str
    logical_index: int = Field(default=0, ge=0)
    transport_attempts: int = Field(default=0, ge=0)


class ResearchSource(BaseModel):
    """Stable provenance identity independent of any individual retrieval."""

    source_record_id: str
    provider: str
    original_url: str | None = None
    canonical_url: str | None = None
    title: str
    first_seen_at: str


class ResearchSourceSnapshot(BaseModel):
    """One versioned search or extraction observation for a source."""

    snapshot_id: str
    source_record_id: str
    citation_label: str
    query_id: str | None = None
    rank: int | None = Field(default=None, ge=1)
    snippet: str = ""
    published_at: str | None = None
    retrieved_at: str
    extractor_version: str | None = None
    extraction_status: str = "not_requested"
    content_hash: str | None = None
    extracted_text_ref: str | None = None
    retention_policy: str = "default"
    expires_at: str | None = None


class ResearchWarning(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ResearchDiagnostics(BaseModel):
    provider: str | None = None
    coverage: str | None = None
    planner_backend: str | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)
    logical_queries: int = Field(default=0, ge=0)
    transport_attempts: int = Field(default=0, ge=0)
    source_count: int = Field(default=0, ge=0)
    snapshot_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchEvidence(BaseModel):
    evidence_id: str
    claim: str
    source_snapshot_ids: list[str] = Field(default_factory=list)
    contradicting_snapshot_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: str = ""


class ResearchAnswerSection(BaseModel):
    kind: ResearchSectionKind
    text: str
    source_snapshot_ids: list[str] = Field(default_factory=list)


class QuickSearchResult(BaseModel):
    mode: Literal["quick"] = "quick"
    query: ResearchQuery
    context_blocks: list[str] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    snapshots: list[ResearchSourceSnapshot] = Field(default_factory=list)
    answer_sections: list[ResearchAnswerSection] = Field(default_factory=list)
    diagnostics: ResearchDiagnostics = Field(default_factory=ResearchDiagnostics)
    warnings: list[ResearchWarning] = Field(default_factory=list)


class DeepResearchResult(BaseModel):
    mode: Literal["deep"] = "deep"
    job_id: str
    research_status: ResearchStatus
    objective: str
    evidence: list[ResearchEvidence] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    synthesis: str = ""
    answer_sections: list[ResearchAnswerSection] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    snapshots: list[ResearchSourceSnapshot] = Field(default_factory=list)
    diagnostics: ResearchDiagnostics = Field(default_factory=ResearchDiagnostics)
    warnings: list[ResearchWarning] = Field(default_factory=list)


ResearchResult = Annotated[
    Union[QuickSearchResult, DeepResearchResult],
    Field(discriminator="mode"),
]


class ResearchMessageMetadata(BaseModel):
    research_mode: ResearchMode
    research_status: ResearchStatus | None = None
    research_job_id: str | None = None
    source_manifest_id: str | None = None
    warning: str | None = None
