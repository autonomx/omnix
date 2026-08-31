"""Semantic task contract and deterministic compiler for generalized Agent routing.

The LLM may describe user intent and references. Omnix owns all derivation of
lanes, profiles, capabilities, evidence policy, and ambiguity handling.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import (
    EvidenceDecision,
    EvidencePolicy,
    EvidenceRequirement,
    EvidenceSourceOption,
    SubjectRef,
)
from .evidence import freshness_max_age_seconds, resolve_subject


SemanticTarget = Literal[
    "conversation",
    "workspace",
    "repository",
    "repository_ci",
    "operations",
    "home",
    "home_energy",
    "email",
    "calendar",
    "contacts",
    "market",
    "market_quote",
    "market_filing",
    "market_status",
    "weather",
    "software_release",
    "public_web",
]
SemanticOperationKind = Literal[
    "read",
    "inspect",
    "modify",
    "execute",
    "validate",
    "send",
    "draft",
    "create",
    "research",
    "compare",
    "explain",
    "compose",
]
SemanticAmbiguity = Literal[
    "none",
    "resolvable_from_context",
    "clarification_required",
]
SemanticObjectiveRelation = Literal[
    "none",
    "continue",
    "resume",
    "revise",
]


class SemanticSubject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target: SemanticTarget
    reference: str = Field(min_length=1, max_length=240)
    kind: str | None = Field(default=None, max_length=80)


class SemanticOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: SemanticOperationKind
    target: SemanticTarget
    subject_reference: str | None = Field(default=None, max_length=240)


class SemanticDataDependency(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target: SemanticTarget
    freshness: Literal["timeless", "current"] = "current"
    subject_reference: str | None = Field(default=None, max_length=240)
    required: bool = True


class SemanticTask(BaseModel):
    """Untrusted semantic description of the user's requested task.

    This model deliberately contains no lane, profile, capability, evidence
    source class, trust floor, or fallback-policy fields. Those are Omnix policy.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: str = Field(min_length=1, max_length=160)
    subjects: list[SemanticSubject] = Field(default_factory=list, max_length=12)
    operations: list[SemanticOperation] = Field(default_factory=list, max_length=16)
    data_dependencies: list[SemanticDataDependency] = Field(default_factory=list, max_length=12)
    autonomous: bool = False
    multi_step: bool = False
    objective_relation: SemanticObjectiveRelation = "none"
    ambiguity: SemanticAmbiguity = "none"
    candidate_interpretations: list[str] = Field(default_factory=list, max_length=6)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    reason_code: str = Field(default="semantic_task", min_length=1, max_length=96)

    @model_validator(mode="after")
    def normalize_ambiguity(self) -> "SemanticTask":
        if self.ambiguity == "none" and self.candidate_interpretations:
            return self.model_copy(update={"candidate_interpretations": []})
        return self


class SemanticCompilerAnomaly(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    detail: str
    rejected_operation: str | None = None


class SemanticTaskCompilation(BaseModel):
    """Deterministic execution interpretation derived from SemanticTask."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lane: Literal["chat", "agent"]
    profile_id: Literal[
        "coding",
        "house",
        "research",
        "personal-assistant",
        "ops",
        "trading-research",
    ] | None = None
    action_intents: list[str] = Field(default_factory=list)
    evidence_decision: EvidenceDecision = Field(default_factory=EvidenceDecision)
    ambiguity: SemanticAmbiguity = "none"
    requires_clarification: bool = False
    reason_code: str = "semantic_task"
    anomalies: list[SemanticCompilerAnomaly] = Field(default_factory=list)
    denied_actions: list[str] = Field(default_factory=list)
    multi_step: bool = False
    autonomous: bool = False


_OPERATION_ACTIONS: dict[tuple[str, str], str] = {
    ("read", "workspace"): "workspace_read",
    ("inspect", "workspace"): "workspace_read",
    ("read", "repository"): "workspace_read",
    ("inspect", "repository"): "workspace_read",
    ("read", "repository_ci"): "workspace_execute",
    ("inspect", "repository_ci"): "workspace_execute",
    ("modify", "workspace"): "workspace_mutate",
    ("modify", "repository"): "workspace_mutate",
    ("execute", "workspace"): "workspace_execute",
    ("execute", "repository"): "workspace_execute",
    ("validate", "workspace"): "workspace_execute",
    ("validate", "repository"): "workspace_execute",
    ("read", "operations"): "ops_read",
    ("inspect", "operations"): "ops_read",
    ("execute", "operations"): "ops_execute",
    ("validate", "operations"): "ops_execute",
    ("read", "home"): "home_read",
    ("inspect", "home"): "home_read",
    ("modify", "home"): "home_mutate",
    ("execute", "home"): "home_mutate",
    ("read", "home_energy"): "home_read",
    ("inspect", "home_energy"): "home_read",
    ("read", "email"): "email_read",
    ("inspect", "email"): "email_read",
    ("draft", "email"): "email_draft",
    ("compose", "email"): "email_draft",
    ("send", "email"): "email_send",
    ("read", "calendar"): "calendar_read",
    ("inspect", "calendar"): "calendar_read",
    ("create", "calendar"): "calendar_create",
    ("modify", "calendar"): "calendar_create",
    ("read", "contacts"): "contacts_read",
    ("inspect", "contacts"): "contacts_read",
    ("read", "market"): "market_read",
    ("inspect", "market"): "market_read",
    ("research", "market"): "market_read",
    ("compare", "market"): "market_read",
    ("read", "market_quote"): "market_read",
    ("inspect", "market_quote"): "market_read",
    ("research", "market_quote"): "market_read",
    ("compare", "market_quote"): "market_read",
    ("read", "market_filing"): "market_read",
    ("research", "market_filing"): "market_read",
    ("compare", "market_filing"): "market_read",
    ("inspect", "market_filing"): "market_read",
    ("read", "market_status"): "market_read",
    ("inspect", "market_status"): "market_read",
    ("read", "weather"): "research_read",
    ("inspect", "weather"): "research_read",
    ("research", "weather"): "research_read",
    ("compare", "weather"): "research_read",
    ("read", "software_release"): "research_read",
    ("inspect", "software_release"): "research_read",
    ("research", "software_release"): "research_read",
    ("compare", "software_release"): "research_read",
    ("read", "public_web"): "research_read",
    ("inspect", "public_web"): "research_read",
    ("research", "public_web"): "research_read",
    ("compare", "public_web"): "research_read",
}


_ACTION_PROFILES: dict[str, str] = {
    "workspace_read": "coding",
    "workspace_execute": "coding",
    "workspace_mutate": "coding",
    "ops_read": "ops",
    "ops_execute": "ops",
    "home_read": "house",
    "home_mutate": "house",
    "email_read": "personal-assistant",
    "email_draft": "personal-assistant",
    "email_send": "personal-assistant",
    "calendar_read": "personal-assistant",
    "calendar_create": "personal-assistant",
    "contacts_read": "personal-assistant",
    "market_read": "trading-research",
    "research_read": "research",
}

_SUBJECT_PROFILES: dict[str, str] = {
    "workspace": "coding",
    "repository": "coding",
    "repository_ci": "coding",
    "operations": "ops",
    "home": "house",
    "home_energy": "house",
    "email": "personal-assistant",
    "calendar": "personal-assistant",
    "contacts": "personal-assistant",
    "market": "trading-research",
    "market_quote": "trading-research",
    "market_filing": "trading-research",
    "market_status": "trading-research",
    "weather": "research",
    "software_release": "research",
    "public_web": "research",
}


# Evidence policy is runtime policy, not LLM output.
# target -> (source_class, trust_floor, fallback_policy)
_EVIDENCE_POLICY: dict[str, tuple[str, str, str]] = {
    "repository": ("repo_contents", "authoritative", "fail_closed"),
    "repository_ci": ("repo_ci_state", "authoritative", "fail_closed"),
    "home": ("home_state", "authoritative", "fail_closed"),
    "home_energy": ("home_energy", "authoritative", "fail_closed"),
    "email": ("email_state", "authoritative", "fail_closed"),
    "calendar": ("calendar_state", "authoritative", "fail_closed"),
    "market": ("market_news", "reputable", "allow_fallback"),
    "market_quote": ("market_quote", "authoritative", "fail_closed"),
    "market_filing": ("company_filing", "primary", "fail_closed"),
    "market_status": ("market_status", "authoritative", "fail_closed"),
    "weather": ("weather_state", "authoritative", "fail_closed"),
    "software_release": ("software_release", "primary", "allow_fallback"),
    "public_web": ("general_current_web", "reputable", "allow_fallback"),
}


_PUBLIC_READ_TARGETS = {
    "market",
    "market_quote",
    "market_filing",
    "market_status",
    "weather",
    "software_release",
    "public_web",
}


def _reference_for_target(task: SemanticTask, target: str) -> str | None:
    """Resolve a parser-supplied subject reference without making it authority."""

    for dependency in task.data_dependencies:
        if dependency.target == target and dependency.subject_reference:
            return dependency.subject_reference.strip() or None
    for operation in task.operations:
        if operation.target == target and operation.subject_reference:
            return operation.subject_reference.strip() or None
    for subject in task.subjects:
        if subject.target == target and subject.reference:
            return subject.reference.strip() or None
    return None


def _explicit_location_subject(reference: str) -> SubjectRef | None:
    clean = " ".join(str(reference or "").split()).strip(" .!?")
    if not clean:
        return None
    canonical = clean.casefold()
    return SubjectRef(
        type="location",
        canonical_id=canonical,
        display_name=clean,
    )


def _evidence_requirement(
    latest_user_message: str,
    dependency: SemanticDataDependency,
    task: SemanticTask,
) -> EvidenceRequirement | None:
    policy = _EVIDENCE_POLICY.get(dependency.target)
    if policy is None or not dependency.required:
        return None
    source_class, trust_floor, fallback_policy = policy
    freshness = dependency.freshness
    reference = dependency.subject_reference or _reference_for_target(task, dependency.target)
    if source_class == "weather_state":
        location_reference = dependency.subject_reference
        if not location_reference:
            location_reference = next(
                (
                    subject.reference
                    for subject in task.subjects
                    if subject.target == dependency.target
                    and str(subject.kind or "").casefold()
                    in {"location", "place", "city", "region"}
                ),
                None,
            )
        subject = (
            _explicit_location_subject(location_reference)
            if location_reference
            else resolve_subject(reference or latest_user_message, source_class)
        )
    else:
        subject = resolve_subject(reference or latest_user_message, source_class)
        if (
            subject is None
            and reference
            and source_class in {"market_quote", "market_news", "company_filing"}
        ):
            # Semantic references may be the bare resolved symbol ("GME") while
            # the legacy text extractor deliberately requires market context.
            # Supplying deterministic context here binds evidence more tightly;
            # it never grants authority.
            subject = resolve_subject(f"stock {reference}", source_class)
    return EvidenceRequirement(
        id=f"semantic-task-{source_class}",
        source_class=source_class,
        subject=subject,
        freshness=freshness,
        trust_floor=trust_floor,
        acceptable_sources=[
            EvidenceSourceOption(
                source_class=source_class,
                trust_floor=trust_floor,
                preference=0,
            )
        ],
        fallback_policy=fallback_policy,
        max_age_seconds=(
            freshness_max_age_seconds(source_class)
            if freshness == "current"
            else None
        ),
    )


def _profile_for_actions(actions: list[str]) -> tuple[str | None, list[SemanticCompilerAnomaly]]:
    profiles = {
        _ACTION_PROFILES[action]
        for action in actions
        if action in _ACTION_PROFILES
    }
    if not profiles:
        return None, []
    if len(profiles) == 1:
        return next(iter(profiles)), []
    # Market research is a specialization of public research. The trading
    # research profile already contains governed web-search authority, so a
    # market task that also needs public-web research is one profile, not a
    # cross-domain composite.
    if profiles == {"research", "trading-research"}:
        return "trading-research", []
    ordered = sorted(profiles)
    return None, [
        SemanticCompilerAnomaly(
            code="unsupported_composite_profiles",
            detail="semantic task spans profiles: " + ", ".join(ordered),
        )
    ]


def _has_stateful_actions(actions: list[str]) -> bool:
    return any(
        action.startswith(("workspace_", "ops_", "home_", "email_", "calendar_", "contacts_"))
        for action in actions
    )


def compile_semantic_task(
    latest_user_message: str,
    task: SemanticTask,
) -> SemanticTaskCompilation:
    """Compile semantic facts into an execution domain without granting authority."""

    actions: list[str] = []
    anomalies: list[SemanticCompilerAnomaly] = []
    for operation in task.operations:
        action = _OPERATION_ACTIONS.get((operation.kind, operation.target))
        if action is not None:
            if action not in actions:
                actions.append(action)
            continue
        if operation.target == "conversation" and operation.kind in {"explain", "compose"}:
            continue
        anomalies.append(
            SemanticCompilerAnomaly(
                code="unsupported_semantic_operation",
                detail=f"{operation.kind}:{operation.target}",
                rejected_operation=f"{operation.kind}:{operation.target}",
            )
        )

    profile_id, profile_anomalies = _profile_for_actions(actions)
    anomalies.extend(profile_anomalies)

    subject_profiles = {
        _SUBJECT_PROFILES[subject.target]
        for subject in task.subjects
        if subject.target in _SUBJECT_PROFILES
    }
    if len(subject_profiles) == 1:
        expected_profile = next(iter(subject_profiles))
        for action in actions:
            action_profile = _ACTION_PROFILES.get(action)
            if action_profile is None or action_profile == expected_profile:
                continue
            anomalies.append(
                SemanticCompilerAnomaly(
                    code="unexpected_cross_domain_action",
                    detail=(
                        f"subjects imply {expected_profile}, but semantic operation "
                        f"implies {action_profile}"
                    ),
                    rejected_operation=action,
                )
            )

    dependencies: list[SemanticDataDependency] = list(task.data_dependencies)

    # Some private/stateful reads inherently depend on the current private state.
    # Mutation does not automatically imply inbox/calendar reads; the parser must
    # state those dependencies when the task actually depends on them.
    implicit_dependencies: list[tuple[str, str]] = []
    if "home_read" in actions or "home_mutate" in actions:
        implicit_dependencies.append(("home", "current"))
    if any(
        operation.target == "home_energy"
        and operation.kind in {"read", "inspect"}
        for operation in task.operations
    ):
        implicit_dependencies.append(("home_energy", "current"))
    if "email_read" in actions:
        implicit_dependencies.append(("email", "current"))
    if "calendar_read" in actions:
        implicit_dependencies.append(("calendar", "current"))

    # These semantic targets inherently name external/current state. The model
    # may state the dependency explicitly (and override freshness), but Omnix
    # does not rely on it remembering a duplicate field before issuing evidence
    # policy.
    implicit_external_freshness = {
        "repository_ci": "current",
        "market": "timeless",
        "market_quote": "current",
        "market_filing": "timeless",
        "market_status": "current",
        "weather": "current",
        "software_release": "timeless",
        "public_web": "timeless",
    }
    for operation in task.operations:
        freshness = implicit_external_freshness.get(operation.target)
        if freshness is not None and operation.kind in {
            "read",
            "inspect",
            "research",
            "compare",
        }:
            implicit_dependencies.append((operation.target, freshness))

    for target, freshness in implicit_dependencies:
        if not any(dep.target == target for dep in dependencies):
            dependencies.append(
                SemanticDataDependency(
                    target=target,
                    freshness=freshness,
                    subject_reference=_reference_for_target(task, target),
                    required=True,
                )
            )

    requirements: list[EvidenceRequirement] = []
    seen_sources: set[str] = set()
    for dependency in dependencies:
        requirement = _evidence_requirement(latest_user_message, dependency, task)
        if requirement is None:
            continue
        if (
            requirement.source_class in {"market_quote", "company_filing"}
            and requirement.subject is None
        ):
            anomalies.append(
                SemanticCompilerAnomaly(
                    code="unresolved_evidence_subject",
                    detail=(
                        f"{requirement.source_class} requires a resolved subject; "
                        f"semantic target {dependency.target} did not provide one"
                    ),
                    rejected_operation=dependency.target,
                )
            )
        if requirement.source_class in seen_sources:
            continue
        seen_sources.add(requirement.source_class)
        requirements.append(requirement)

    lowered = " ".join(str(latest_user_message or "").casefold().split())
    external_forbidden = any(
        phrase in lowered
        for phrase in (
            "without using the web",
            "without the web",
            "do not use the web",
            "don't use the web",
            "never use the web",
            "without using the internet",
            "do not use the internet",
            "don't use the internet",
            "from memory only",
        )
    )
    attribution = (
        "required"
        if any(
            phrase in lowered
            for phrase in ("with sources", "cite sources", "citations", "sourced")
        )
        else "when_used"
    )
    evidence_decision = EvidenceDecision(
        policy=EvidencePolicy(
            requirement="required" if requirements else "none",
            external_access="forbidden" if external_forbidden else "allowed",
            requirements=requirements,
            user_visible_attribution=attribution,
            retrieval={"strategy": "adaptive"},
        ),
        confidence=1.0,
        reason=f"semantic_task_compiler:{task.reason_code}"[:240],
        classifier="deterministic",
    )

    public_read_only = bool(actions) and set(actions) <= {"research_read", "market_read"}
    stateful = _has_stateful_actions(actions)
    unsafe_semantic_anomaly = any(
        anomaly.code in {
            "unsupported_composite_profiles",
            "unexpected_cross_domain_action",
            "unsupported_semantic_operation",
            "unresolved_evidence_subject",
        }
        for anomaly in anomalies
    )
    requires_clarification = (
        task.ambiguity == "clarification_required"
        or unsafe_semantic_anomaly
    )

    if requires_clarification:
        lane: Literal["chat", "agent"] = "chat"
    elif stateful:
        lane = "agent"
    elif public_read_only:
        # Bounded current/public reads remain Chat; open-ended autonomous
        # research becomes Agent.
        lane = "agent" if task.autonomous or task.multi_step else "chat"
    elif task.autonomous and task.multi_step:
        lane = "agent"
    else:
        lane = "chat"

    if lane == "agent" and profile_id is None:
        # Autonomous reasoning/research without stateful operations uses the
        # research profile. This is derived policy, not model-selected profile.
        profile_id = "research"

    return SemanticTaskCompilation(
        lane=lane,
        profile_id=profile_id,
        action_intents=actions,
        evidence_decision=evidence_decision,
        ambiguity=task.ambiguity,
        requires_clarification=requires_clarification,
        reason_code=task.reason_code,
        anomalies=anomalies,
        denied_actions=list(
            dict.fromkeys(
                anomaly.rejected_operation
                for anomaly in anomalies
                if anomaly.rejected_operation
            )
        ),
        multi_step=task.multi_step,
        autonomous=task.autonomous,
    )


def semantic_task_from_legacy(decision: object) -> SemanticTask:
    """Compatibility adapter for tests/extensions that still emit v1 decisions."""

    operations: list[SemanticOperation] = []
    action_map: dict[str, tuple[str, str]] = {
        "workspace_read": ("inspect", "workspace"),
        "workspace_execute": ("execute", "workspace"),
        "workspace_mutate": ("modify", "workspace"),
        "home_read": ("inspect", "home"),
        "home_mutate": ("modify", "home"),
        "email_read": ("read", "email"),
        "email_draft": ("draft", "email"),
        "email_send": ("send", "email"),
        "calendar_read": ("read", "calendar"),
        "calendar_create": ("create", "calendar"),
        "contacts_read": ("read", "contacts"),
        "research_read": ("research", "public_web"),
        "market_read": ("research", "market"),
    }
    for raw in list(getattr(decision, "action_intents", []) or []):
        mapped = action_map.get(str(raw))
        if mapped is None:
            continue
        operations.append(SemanticOperation(kind=mapped[0], target=mapped[1]))

    source_to_target = {
        "general_current_web": "public_web",
        "breaking_news": "public_web",
        "market_news": "market",
        "company_filing": "market_filing",
        "software_release": "software_release",
        "repo_contents": "repository",
        "repo_ci_state": "repository_ci",
        "home_state": "home",
        "home_energy": "home_energy",
        "calendar_state": "calendar",
        "email_state": "email",
        "market_quote": "market_quote",
        "market_status": "market_status",
        "weather_state": "weather",
    }
    dependencies: list[SemanticDataDependency] = []
    for row in list(getattr(decision, "evidence_requirements", []) or []):
        target = source_to_target.get(str(getattr(row, "source_class", "")))
        if target is None:
            continue
        dependencies.append(
            SemanticDataDependency(
                target=target,
                freshness=str(getattr(row, "freshness", "current") or "current"),
                required=True,
            )
        )

    return SemanticTask(
        intent=str(
            getattr(decision, "primary_intent", None)
            or "legacy_semantic_task"
        )[:160],
        operations=operations,
        data_dependencies=dependencies,
        autonomous=str(getattr(decision, "lane", "chat")) == "agent",
        multi_step=bool(getattr(decision, "multi_step", False)),
        ambiguity="none",
        confidence=float(getattr(decision, "confidence", 0.75) or 0.75),
        reason_code="legacy_semantic_v1",
    )


__all__ = [
    "SemanticAmbiguity",
    "SemanticCompilerAnomaly",
    "SemanticDataDependency",
    "SemanticOperation",
    "SemanticSubject",
    "SemanticTask",
    "SemanticTaskCompilation",
    "compile_semantic_task",
    "semantic_task_from_legacy",
]
