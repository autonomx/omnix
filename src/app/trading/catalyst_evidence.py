from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


CatalystSourceType = Literal["sec", "company", "news", "manual"]


class CatalystEvidence(BaseModel):
    """Timestamped immutable evidence; never a naked bullish/bearish flag."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    instrument_id: str
    source_type: CatalystSourceType
    source_locator: str
    published_at: datetime
    captured_at: datetime
    headline: str | None = None
    text_hash: str = Field(min_length=64, max_length=64)
    facts: dict[str, object] = Field(default_factory=dict)
    dilution_flags: tuple[str, ...] = ()
    immutable_fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("published_at", "captured_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("catalyst evidence timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class CatalystShadowClassification(BaseModel):
    """Read-only classifier output. It is not an execution authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    classifier_id: str
    classifier_version: str
    catalyst_class: Literal[
        "earnings",
        "regulatory",
        "contract_partnership",
        "financing",
        "corporate_action",
        "clinical",
        "legal",
        "other",
        "unknown",
    ] = "unknown"
    directional_bias: Literal["positive", "negative", "mixed", "unknown"] = "unknown"
    novelty: Literal["new", "recycled", "unclear"] = "unclear"
    dilution_risk: Literal["none_seen", "possible", "explicit", "unknown"] = "unknown"
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence_ids: tuple[str, ...]
    rationale: str = ""
    shadow_only: Literal[True] = True


class CatalystClassifier(Protocol):
    def classify(self, evidence: tuple[CatalystEvidence, ...]) -> CatalystShadowClassification: ...


_DILUTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("registered_offering", re.compile(r"\b(registered direct|public offering|securities offering)\b", re.I)),
    ("atm", re.compile(r"\b(at-the-market|ATM offering|sales agreement)\b", re.I)),
    ("warrants", re.compile(r"\bwarrants?\b", re.I)),
    ("convertible", re.compile(r"\bconvertible (?:note|notes|debt|preferred)\b", re.I)),
    ("shelf_registration", re.compile(r"\bshelf registration\b", re.I)),
    ("resale_registration", re.compile(r"\bresale registration\b", re.I)),
    ("equity_line", re.compile(r"\bequity line\b", re.I)),
)


def dilution_flags(text: str) -> tuple[str, ...]:
    return tuple(name for name, pattern in _DILUTION_PATTERNS if pattern.search(text))


def capture_catalyst_evidence(
    *,
    evidence_id: str,
    instrument_id: str,
    source_type: CatalystSourceType,
    source_locator: str,
    published_at: datetime,
    raw_text: str,
    headline: str | None = None,
    captured_at: datetime | None = None,
    facts: dict[str, object] | None = None,
) -> CatalystEvidence:
    captured = captured_at or datetime.now(timezone.utc)
    normalized = " ".join(raw_text.split())
    text_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    flags = dilution_flags(normalized)
    payload = {
        "evidence_id": evidence_id,
        "instrument_id": instrument_id,
        "source_type": source_type,
        "source_locator": source_locator,
        "published_at": published_at.astimezone(timezone.utc).isoformat(),
        "captured_at": captured.astimezone(timezone.utc).isoformat(),
        "headline": headline,
        "text_hash": text_hash,
        "facts": facts or {},
        "dilution_flags": flags,
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return CatalystEvidence(
        **payload,
        immutable_fingerprint=fingerprint,
    )


def classify_catalyst_shadow(
    evidence: list[CatalystEvidence] | tuple[CatalystEvidence, ...],
    classifier: CatalystClassifier,
) -> CatalystShadowClassification:
    """Invoke an LLM/deterministic classifier strictly as a shadow annotation."""
    frozen = tuple(sorted(evidence, key=lambda item: (item.published_at, item.evidence_id)))
    output = classifier.classify(frozen)
    expected_ids = tuple(item.evidence_id for item in frozen)
    if tuple(sorted(output.evidence_ids)) != tuple(sorted(expected_ids)):
        raise ValueError("catalyst classifier must cite exactly the supplied evidence ids")
    if output.shadow_only is not True:
        raise ValueError("catalyst classifier output must remain shadow-only")
    return output
