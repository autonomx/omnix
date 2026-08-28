"""Evidence classification, source resolution, capability compilation, and evaluation.

Pi owns execution strategy. Omnix owns the evidence contract, authority issued to
the run, provenance receipts, and completion acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Callable

from .contracts import (
    EvidenceDecision,
    EvidencePolicy,
    EvidenceReceipt,
    EvidenceRequirement,
    EvidenceRequirementEvaluation,
    EvidenceSet,
    EvidenceSourceOption,
    RequestModeCandidate,
    RequestModeSelection,
    SubjectRef,
)
from .profiles import AgentProfile, profile_external_ceiling

_CURRENT = re.compile(r"\b(?:today|current(?:ly)?|latest|right now|this (?:week|month|year)|recent|newest|news)\b", re.I)
_NO_EXTERNAL = re.compile(r"\b(?:without (?:the )?(?:internet|web)|do not (?:search|browse)|don't (?:search|browse)|from memory only)\b", re.I)
_SOURCE_REQUEST = re.compile(r"\b(?:find|give|provide|include|cite)\b.{0,40}\b(?:sources?|citations?|evidence)\b|\bresearch\b", re.I)
_MARKET = re.compile(r"\b(?:stock|stocks|ticker|market|shares?|equity|nvda|gme|tsla|\$[A-Z]{1,5})\b", re.I)
_QUOTE = re.compile(r"\b(?:price|quote|trading at|last trade|bid|ask)\b", re.I)
_CI = re.compile(r"\b(?:ci|github actions?|workflow checks?|checks? (?:failed|passing|status)|build status)\b", re.I)
_REPO = re.compile(r"\b(?:repo(?:sitory)?|github|pull request|\bpr\s*#?\d+|branch|commit)\b", re.I)
_WEATHER = re.compile(r"\b(?:weather|raining|rain|snow|temperature|forecast)\b", re.I)
_HOME = re.compile(r"\b(?:home|lamp|light|plug|outlet|thermostat|kasa)\b", re.I)
_CALENDAR = re.compile(r"\b(?:calendar|meeting|appointment|schedule)\b", re.I)
_EMAIL = re.compile(r"\b(?:gmail|email|inbox|message)\b", re.I)
_FILINGS = re.compile(r"\b(?:10-k|10-q|8-k|sec filing|company filing|filings)\b", re.I)
_RELEASE = re.compile(r"\b(?:release|version|changelog|released)\b", re.I)
_CONCEPTUAL = re.compile(r"^(?:what is|what are|explain|describe|teach me|how does|why does|compare)\b", re.I)
_TICKER = re.compile(r"(?:\$([A-Z]{1,5})\b|\b(NVDA|GME|TSLA)\b)")
_PR = re.compile(r"\bPR\s*#?(\d+)\b", re.I)

TRUST_RANK = {"general": 0, "reputable": 1, "primary": 2, "authoritative": 3}
FRESHNESS_SECONDS = {
    "market_quote": 60,
    "market_status": 60,
    "repo_ci_state": 300,
    "weather_state": 1800,
    "breaking_news": 21600,
    "market_news": 21600,
    "software_release": 86400,
    "company_leadership": 86400,
    "general_current_web": 86400,
}

SOURCE_CAPABILITIES: dict[str, tuple[str, str]] = {
    "general_current_web": ("research.web_search", "reputable"),
    "breaking_news": ("research.web_search", "reputable"),
    "market_news": ("research.web_search", "reputable"),
    "company_filing": ("research.web_search", "primary"),
    "software_release": ("research.web_search", "primary"),
    "repo_contents": ("github.read_repo", "authoritative"),
    "repo_ci_state": ("github.inspect_ci", "authoritative"),
    "home_state": ("home.get_state", "authoritative"),
    "home_energy": ("home.get_energy", "authoritative"),
    "calendar_state": ("calendar.read_availability", "authoritative"),
    "email_state": ("gmail.read_email", "authoritative"),
    # Intentionally no web fallback: a quote/weather request fails compilation
    # until an authoritative provider capability exists in the profile ceiling.
    "market_quote": ("market.quote", "authoritative"),
    "market_status": ("market.status", "authoritative"),
    "weather_state": ("weather.current", "authoritative"),
}

class EvidenceCompilationError(ValueError):
    def __init__(self, code: str, message: str, *, requirement_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.requirement_id = requirement_id


@dataclass(frozen=True)
class CompiledEvidence:
    decision: EvidenceDecision
    required_local: tuple[str, ...]
    required_external: tuple[str, ...]


def resolve_request_mode(
    content: str,
    *,
    turn_research_mode: str | None,
    persistent_agent: bool,
    classifier_lane: str,
) -> RequestModeSelection:
    text = str(content or "").strip()
    candidates: list[RequestModeCandidate] = []
    if re.match(r"^(?:/agent\b|/agnet\b|agent[,:]\s|use (?:the )?agent\b)", text, re.I):
        candidates.append(RequestModeCandidate(mode="agent", source="explicit_command", priority=500))
    normalized = str(turn_research_mode or "").strip().casefold()
    if normalized == "quick":
        candidates.append(RequestModeCandidate(mode="quick_research", source="turn_setting", priority=400))
    elif normalized == "deep":
        candidates.append(RequestModeCandidate(mode="deep_research", source="turn_setting", priority=400))
    if persistent_agent:
        candidates.append(RequestModeCandidate(mode="agent", source="persistent_setting", priority=300))
    if classifier_lane == "agent":
        candidates.append(RequestModeCandidate(mode="agent", source="classifier", priority=200))
    elif classifier_lane in {"chat", "direct", "workflow"}:
        candidates.append(RequestModeCandidate(mode="auto", source="classifier", priority=200))
    candidates.append(RequestModeCandidate(mode="chat", source="default", priority=0))
    ordered = sorted(enumerate(candidates), key=lambda row: (-row[1].priority, row[0]))
    winner = ordered[0][1]
    suppressed = [row for _, row in ordered[1:]]
    return RequestModeSelection(
        mode=winner.mode,
        source=winner.source,
        priority=winner.priority,
        suppressed=suppressed,
    )


def resolve_subject(task: str, source_class: str) -> SubjectRef | None:
    text = str(task or "")
    if source_class in {"market_quote", "market_news", "market_status", "company_filing"}:
        match = _TICKER.search(text.upper())
        if match:
            ticker = (match.group(1) or match.group(2) or "").upper()
            return SubjectRef(
                type="security",
                canonical_id=f"{ticker}:US",
                display_name=ticker,
                qualifiers={"ticker": ticker},
            )
    if source_class in {"repo_ci_state", "repo_contents"}:
        pr = _PR.search(text)
        qualifiers = {"pull_request": int(pr.group(1))} if pr else {}
        return SubjectRef(
            type="repository_ref",
            canonical_id="current_repository",
            display_name="current repository",
            qualifiers=qualifiers,
        )
    if source_class == "weather_state":
        return SubjectRef(type="location", canonical_id="user_location", display_name="user location")
    if source_class in {"home_state", "home_energy"}:
        return SubjectRef(type="home", canonical_id="current_home", display_name="current home")
    if source_class == "calendar_state":
        return SubjectRef(type="calendar", canonical_id="primary_calendar", display_name="primary calendar")
    if source_class == "email_state":
        return SubjectRef(type="mailbox", canonical_id="primary_mailbox", display_name="primary mailbox")
    return None


def _requirement(
    task: str,
    source_class: str,
    *,
    freshness: str = "current",
    trust: str | None = None,
    fallback: str = "fail_closed",
) -> EvidenceRequirement:
    _, default_trust = SOURCE_CAPABILITIES.get(source_class, ("", "reputable"))
    source_trust = trust or default_trust
    return EvidenceRequirement(
        id=f"evidence-{source_class}",
        source_class=source_class,
        subject=resolve_subject(task, source_class),
        freshness=freshness,
        trust_floor=source_trust,
        acceptable_sources=[
            EvidenceSourceOption(source_class=source_class, trust_floor=source_trust)
        ],
        fallback_policy=fallback,
        max_age_seconds=FRESHNESS_SECONDS.get(source_class) if freshness == "current" else None,
    )


def classify_evidence(
    task: str,
    *,
    profile_id: str,
    semantic_adviser: Callable[[str, str], EvidenceDecision | None] | None = None,
) -> EvidenceDecision:
    text = " ".join(str(task or "").split())
    external_forbidden = bool(_NO_EXTERNAL.search(text))
    attribution = "required" if re.search(r"\b(?:sourced|with sources|cite sources|citations)\b", text, re.I) else "when_used"
    requirements: list[EvidenceRequirement] = []

    if _MARKET.search(text) and _QUOTE.search(text):
        requirements.append(_requirement(text, "market_quote", trust="authoritative"))
    elif _CI.search(text):
        requirements.append(_requirement(text, "repo_ci_state", trust="authoritative"))
    elif _WEATHER.search(text) and (_CURRENT.search(text) or re.search(r"\boutside\b", text, re.I)):
        requirements.append(_requirement(text, "weather_state", trust="authoritative"))
    elif profile_id == "house" and re.search(r"\b(?:check|inspect|status|state|energy)\b", text, re.I):
        source = "home_energy" if "energy" in text.casefold() else "home_state"
        requirements.append(_requirement(text, source, trust="authoritative"))
    elif profile_id == "personal-assistant" and _CALENDAR.search(text):
        requirements.append(_requirement(text, "calendar_state", trust="authoritative"))
    elif profile_id == "personal-assistant" and _EMAIL.search(text):
        requirements.append(_requirement(text, "email_state", trust="authoritative"))
    elif _FILINGS.search(text):
        requirements.append(_requirement(text, "company_filing", trust="primary"))
    elif _REPO.search(text) and _CURRENT.search(text):
        requirements.append(_requirement(text, "repo_contents", trust="authoritative"))
    elif _RELEASE.search(text) and _CURRENT.search(text):
        requirements.append(_requirement(text, "software_release", trust="primary", fallback="allow_fallback"))
    elif _MARKET.search(text) and (_CURRENT.search(text) or _SOURCE_REQUEST.search(text)):
        requirements.append(_requirement(text, "market_news", trust="reputable", fallback="allow_fallback"))
    elif _CURRENT.search(text):
        requirements.append(_requirement(text, "general_current_web", trust="reputable", fallback="allow_fallback"))
    elif _SOURCE_REQUEST.search(text):
        requirements.append(_requirement(text, "general_current_web", freshness="timeless", trust="reputable", fallback="allow_fallback"))

    if requirements:
        policy = EvidencePolicy(
            requirement="required",
            external_access="forbidden" if external_forbidden else "allowed",
            requirements=requirements,
            user_visible_attribution=attribution,
        )
        return EvidenceDecision(
            policy=policy,
            confidence=0.98 if any(r.source_class != "general_current_web" for r in requirements) else 0.92,
            reason=f"required:{','.join(r.source_class for r in requirements)}",
            classifier="deterministic",
        )

    # Timeless conceptual questions default to model knowledge. Ambiguous tasks
    # can use a semantic adviser, but low-confidence potentially-current tasks
    # conservatively require read-only evidence rather than widening authority.
    if _CONCEPTUAL.search(text):
        return EvidenceDecision(
            policy=EvidencePolicy(
                requirement="none",
                external_access="forbidden" if external_forbidden else "allowed",
                user_visible_attribution=attribution,
            ),
            confidence=0.95,
            reason="timeless_conceptual_request",
            classifier="deterministic",
        )

    if semantic_adviser is not None:
        advised = semantic_adviser(text, profile_id)
        if advised is not None:
            return advised

    potentially_current = profile_id in {"trading-research", "house", "personal-assistant"} and bool(
        _MARKET.search(text) or _HOME.search(text) or _CALENDAR.search(text) or _EMAIL.search(text)
    )
    if potentially_current:
        source = (
            "market_news" if _MARKET.search(text)
            else "home_state" if _HOME.search(text)
            else "calendar_state" if _CALENDAR.search(text)
            else "email_state"
        )
        return EvidenceDecision(
            policy=EvidencePolicy(
                requirement="required",
                external_access="forbidden" if external_forbidden else "allowed",
                requirements=[_requirement(text, source, fallback="allow_fallback" if source == "market_news" else "fail_closed")],
                user_visible_attribution=attribution,
            ),
            confidence=0.55,
            reason=f"conservative_current_domain:{source}",
            classifier="conservative",
        )

    return EvidenceDecision(
        policy=EvidencePolicy(
            requirement="none",
            external_access="forbidden" if external_forbidden else "allowed",
            user_visible_attribution=attribution,
        ),
        confidence=0.75,
        reason="model_knowledge_sufficient",
        classifier="conservative",
    )


def capability_for_requirement(requirement: EvidenceRequirement) -> tuple[str, str]:
    options = [requirement.source_class, *[row.source_class for row in requirement.acceptable_sources]]
    seen: set[str] = set()
    for source_class in options:
        if source_class in seen:
            continue
        seen.add(source_class)
        resolved = SOURCE_CAPABILITIES.get(source_class)
        if resolved:
            return resolved
    raise EvidenceCompilationError(
        "evidence_required_but_unavailable",
        f"no capability mapping exists for evidence source {requirement.source_class}",
        requirement_id=requirement.id,
    )


def compile_evidence(profile: AgentProfile, decision: EvidenceDecision) -> CompiledEvidence:
    policy = decision.policy
    if policy.requirement == "required" and policy.external_access == "forbidden" and policy.requirements:
        raise EvidenceCompilationError(
            "external_evidence_forbidden",
            "required evidence can only be obtained externally, but external access is forbidden",
        )
    ceiling = profile_external_ceiling(profile)
    required_external: list[str] = []
    required_local: list[str] = []
    if policy.requirement == "required":
        for requirement in policy.requirements:
            capability, _trust = capability_for_requirement(requirement)
            if capability.startswith("workspace."):
                if capability not in profile.capabilities:
                    raise EvidenceCompilationError(
                        "required_source_outside_profile_ceiling",
                        f"{capability} is outside profile {profile.id}",
                        requirement_id=requirement.id,
                    )
                required_local.append(capability)
            else:
                if capability not in ceiling:
                    raise EvidenceCompilationError(
                        "required_source_outside_profile_ceiling",
                        f"{capability} is outside profile {profile.id}",
                        requirement_id=requirement.id,
                    )
                required_external.append(capability)
    return CompiledEvidence(
        decision=decision,
        required_local=tuple(dict.fromkeys(required_local)),
        required_external=tuple(dict.fromkeys(required_external)),
    )


def revise_objective(previous: str, instruction: str) -> str:
    clean = " ".join(str(instruction or "").split())
    prior = str(previous or "").strip()
    if not prior:
        return clean
    if re.search(r"^(?:actually|instead|forget that|just\b|do not\b|don't\b)", clean, re.I):
        return clean
    return f"{prior}\nLater steering: {clean}"


def subject_matches(required: SubjectRef | None, observed: SubjectRef | None) -> bool:
    if required is None:
        return True
    if observed is None:
        return False
    if required.type != observed.type or required.canonical_id != observed.canonical_id:
        return False
    for key, value in required.qualifiers.items():
        if key in observed.qualifiers and observed.qualifiers.get(key) != value:
            return False
    return True


def evaluate_evidence_set(
    run_id: str,
    policy: EvidencePolicy,
    receipts: list[EvidenceReceipt],
    *,
    now: datetime | None = None,
) -> EvidenceSet:
    if policy.requirement != "required":
        return EvidenceSet(
            run_id=run_id,
            source_manifest_ids=sorted({r.source_manifest_id for r in receipts if r.source_manifest_id}),
            passed=True,
        )
    current = now or datetime.now(timezone.utc)
    evaluations: list[EvidenceRequirementEvaluation] = []
    missing: list[str] = []
    stale: list[str] = []
    wrong_subject: list[str] = []
    low_trust: list[str] = []

    for requirement in policy.requirements:
        source_classes = {requirement.source_class, *[o.source_class for o in requirement.acceptable_sources]}
        candidates = [r for r in receipts if r.source_class in source_classes]
        matched: list[str] = []
        rejected: list[str] = []
        statuses: list[str] = []
        for receipt in candidates:
            if not subject_matches(requirement.subject, receipt.subject):
                wrong_subject.append(receipt.receipt_id)
                rejected.append(receipt.receipt_id)
                statuses.append("wrong_subject")
                continue
            if TRUST_RANK.get(receipt.trust_level, 0) < TRUST_RANK.get(requirement.trust_floor, 0):
                low_trust.append(receipt.receipt_id)
                rejected.append(receipt.receipt_id)
                statuses.append("insufficient_trust")
                continue
            max_age = requirement.max_age_seconds
            if max_age and (current - receipt.observed_at).total_seconds() > max_age:
                stale.append(receipt.receipt_id)
                rejected.append(receipt.receipt_id)
                statuses.append("stale")
                continue
            matched.append(receipt.receipt_id)

        if len(matched) >= requirement.minimum_matches:
            status = "satisfied"
            reason = None
        elif not candidates:
            status = "missing"
            reason = "no receipt for required source class"
            missing.append(requirement.id)
        elif "stale" in statuses:
            status = "stale"
            reason = "matching receipts are stale"
            missing.append(requirement.id)
        elif "wrong_subject" in statuses:
            status = "wrong_subject"
            reason = "receipts do not match required subject"
            missing.append(requirement.id)
        elif "insufficient_trust" in statuses:
            status = "insufficient_trust"
            reason = "receipts are below trust floor"
            missing.append(requirement.id)
        else:
            status = "rejected"
            reason = "insufficient acceptable receipts"
            missing.append(requirement.id)
        evaluations.append(EvidenceRequirementEvaluation(
            requirement_id=requirement.id,
            status=status,
            matching_receipt_ids=matched,
            rejected_receipt_ids=rejected,
            reason=reason,
        ))

    return EvidenceSet(
        run_id=run_id,
        requirements=evaluations,
        missing_requirements=missing,
        stale_receipts=sorted(set(stale)),
        wrong_subject_receipts=sorted(set(wrong_subject)),
        insufficient_trust_receipts=sorted(set(low_trust)),
        source_manifest_ids=sorted({r.source_manifest_id for r in receipts if r.source_manifest_id}),
        passed=not missing,
    )


def request_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def result_digest(payload: dict[str, object]) -> str:
    return request_digest(payload)
