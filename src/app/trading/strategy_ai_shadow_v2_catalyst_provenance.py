from __future__ import annotations

"""Catalyst-specific provenance policy for AI Shadow v2.

The broader research bundle intentionally contains SEC financing/supply documents.
Those documents are authoritative for supply risk but must not, by themselves,
make the *gap catalyst* appear primary-source verified. This module narrows the
provenance tuple before semantic inference and normalizes the final snapshot after
roadmap-level catalyst validation.
"""

from datetime import timedelta

from . import strategy_ai_shadow_v2 as core
from .research.contracts import TradingEvidence

_SUPPLY_ONLY_FORMS = {"S-1", "S-1/A", "S-3", "S-3/A", "424B3", "424B5", "RW", "EFFECT"}
_INSTALLED = False
_POST_INSTALLED = False
_ROADMAP_ASSESS = None


def _known_time(item: TradingEvidence):
    return item.omnix_known_at or item.captured_at


def _catalyst_quality_evidence(
    evidence: list[TradingEvidence] | tuple[TradingEvidence, ...],
) -> list[TradingEvidence]:
    if not evidence:
        return []
    reference = max(_known_time(item) for item in evidence)
    lower = reference - timedelta(hours=72)
    result: list[TradingEvidence] = []
    for item in evidence:
        if item.source_type in {"news", "web", "manual"}:
            result.append(item)
            continue
        published = item.source_published_at or item.source_available_at or item.captured_at
        if published < lower:
            continue
        if item.source_type == "company_ir":
            result.append(item)
            continue
        if item.source_type == "sec":
            form = str(item.metadata.get("form") or "").upper()
            if form not in _SUPPLY_ONLY_FORMS:
                result.append(item)
    return result


def catalyst_deterministic_evidence_quality(
    evidence: list[TradingEvidence] | tuple[TradingEvidence, ...],
):
    if not evidence:
        return "unresolved", False, 0
    relevant = _catalyst_quality_evidence(evidence)
    primary = [
        item
        for item in relevant
        if item.source_authority_tier == 1 and item.source_type in {"sec", "company_ir"}
    ]
    verified = bool(primary)
    if not relevant:
        return "unresolved", False, 0
    if verified and all(item.source_authority_tier <= 2 for item in relevant):
        quality = "primary_verified"
    elif verified:
        quality = "mixed"
    else:
        quality = "secondary_only"
    score = round(
        sum(max(0, 5 - int(item.source_authority_tier)) for item in relevant)
        / (len(relevant) * 4)
        * 100
    )
    return quality, verified, min(100, score)


def _assess_with_consistent_provenance(self, *args, **kwargs):
    assert _ROADMAP_ASSESS is not None
    snapshot = _ROADMAP_ASSESS(self, *args, **kwargs)
    if snapshot.primary_source_verified:
        return snapshot
    if not snapshot.evidence_ids:
        quality = "unresolved"
    elif snapshot.evidence_quality == "primary_verified":
        # Primary material exists in the bundle, but deterministic catalyst
        # validation did not bind it strongly enough to the current catalyst.
        quality = "mixed"
    else:
        quality = snapshot.evidence_quality
    if quality == snapshot.evidence_quality:
        return snapshot
    return snapshot.model_copy(update={"evidence_quality": quality})


def install_ai_shadow_v2_catalyst_provenance() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    core.deterministic_evidence_quality = catalyst_deterministic_evidence_quality
    _INSTALLED = True


def install_ai_shadow_v2_catalyst_consistency() -> None:
    """Install after the roadmap policy has wrapped Catalyst Intelligence."""

    global _POST_INSTALLED, _ROADMAP_ASSESS
    if _POST_INSTALLED:
        return
    _ROADMAP_ASSESS = core.CatalystIntelligenceAnalyzer.assess
    core.CatalystIntelligenceAnalyzer.assess = _assess_with_consistent_provenance
    _POST_INSTALLED = True


__all__ = [
    "catalyst_deterministic_evidence_quality",
    "install_ai_shadow_v2_catalyst_consistency",
    "install_ai_shadow_v2_catalyst_provenance",
]
