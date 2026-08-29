"""Opt-in live Codex matrix for semantic reclassification after user steering.

Run locally with:

    $env:OMNIX_RUN_LIVE_CODEX_STEERING_TESTS="1"
    $env:OMNIX_LIVE_CODEX_SEMANTIC_MODEL="gpt-5.6-luna"
    $env:OMNIX_LIVE_CODEX_REASONING_EFFORT="xhigh"
    python -m pytest src/tests/agent_runtime/test_live_codex_steering_matrix.py -q --tb=short
"""
from __future__ import annotations

from dataclasses import dataclass
import os

import pytest

from app.agent_runtime.evidence import (
    classify_evidence,
    compile_task_authority,
    evidence_decision_from_semantic,
    revise_objective,
)
from app.agent_runtime.profiles import get_agent_profile
from app.agent_runtime.semantic_classifier import (
    ProviderSemanticIntentClassifier,
    semantic_confidence_threshold,
    semantic_profile_id,
)
from app.providers import ChatGPTCodexProvider, ProviderConfig


_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SteeringCase:
    id: str
    initial: str
    steering: str
    lane: str
    profile: str
    required_actions: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    required_local: tuple[str, ...] = ()
    forbidden_local: tuple[str, ...] = ()
    required_external: tuple[str, ...] = ()
    forbidden_external: tuple[str, ...] = ()


CASES: tuple[SteeringCase, ...] = (
    SteeringCase(
        "coding_add_tests_without_edit",
        "Inspect the recent auth diff.",
        "also run the relevant tests, but don't edit anything.",
        "agent",
        "coding",
        required_actions=("workspace_read", "workspace_execute"),
        forbidden_actions=("workspace_mutate",),
        required_local=("workspace.read", "workspace.command"),
        forbidden_local=("workspace.edit", "workspace.write"),
    ),
    SteeringCase(
        "coding_read_to_fix",
        "Inspect the parser failure and explain it.",
        "Actually fix the parser bug in the repo and run the tests.",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
        required_local=("workspace.edit", "workspace.test"),
    ),
    SteeringCase(
        "coding_fix_to_read_only",
        "Fix the failing parser tests.",
        "Don't change anything; inspect the parser and diagnose the failure.",
        "agent",
        "coding",
        required_actions=("workspace_read",),
        forbidden_actions=("workspace_mutate",),
        forbidden_local=("workspace.edit", "workspace.write"),
    ),
    SteeringCase(
        "email_draft_to_send",
        "Draft a status email to Bob.",
        "Actually send the status email to Bob.",
        "agent",
        "personal-assistant",
        required_actions=("email_send",),
        required_external=("gmail.send_email",),
    ),
    SteeringCase(
        "email_send_to_draft_only",
        "Send Bob a status update.",
        "Actually don't send anything; draft the status reply for me to review.",
        "agent",
        "personal-assistant",
        required_actions=("email_draft",),
        forbidden_actions=("email_send",),
        required_external=("gmail.create_draft",),
        forbidden_external=("gmail.send_email",),
    ),
    SteeringCase(
        "calendar_read_to_create",
        "Check my calendar tomorrow afternoon.",
        "also find a free 30 minute slot and schedule a call with Sam.",
        "agent",
        "personal-assistant",
        required_actions=("calendar_read", "calendar_create"),
        required_evidence=("calendar_state",),
        required_external=("calendar.read_availability", "calendar.create_event"),
    ),
    SteeringCase(
        "home_read_to_mutate",
        "Check whether the bedroom lamp is on.",
        "Actually turn the bedroom lamp off.",
        "agent",
        "house",
        required_actions=("home_mutate",),
        required_external=("home.get_state", "home.set_state"),
    ),
    SteeringCase(
        "home_mutate_to_read_only",
        "Turn off the porch light.",
        "Actually don't change the porch light; just check whether it's on.",
        "agent",
        "house",
        required_actions=("home_read",),
        forbidden_actions=("home_mutate",),
        required_evidence=("home_state",),
        forbidden_external=("home.set_state",),
    ),
    SteeringCase(
        "market_bounded_to_comparative",
        "Check whether NVDA announced anything important today.",
        "Actually compare today's NVDA and AMD catalysts and rank which matters more.",
        "agent",
        "trading-research",
        required_actions=("market_read",),
        required_evidence=("market_news",),
    ),
    SteeringCase(
        "research_add_second_subject",
        "Research the latest stable Python release.",
        "also compare it with the latest stable Node release and summarize the important differences.",
        "agent",
        "research",
        required_actions=("research_read",),
        required_evidence=("software_release",),
        required_external=("research.web_search",),
    ),
    SteeringCase(
        "research_to_memory_only",
        "Research the latest PostgreSQL release.",
        "Actually explain PostgreSQL release versioning from memory only; don't browse the web.",
        "chat",
        "research",
        forbidden_actions=("research_read",),
        forbidden_external=("research.web_search",),
    ),
    SteeringCase(
        "ci_mutation_to_diagnose_only",
        "Fix whatever is making CI red.",
        "Don't change anything; inspect current CI and diagnose the failure only.",
        "agent",
        "coding",
        forbidden_actions=("workspace_mutate",),
        required_evidence=("repo_ci_state",),
        required_local=("workspace.read", "workspace.command"),
        forbidden_local=("workspace.edit", "workspace.write"),
        required_external=("github.inspect_ci",),
    ),
)


def _enabled() -> bool:
    return (
        str(os.environ.get("OMNIX_RUN_LIVE_CODEX_STEERING_TESTS", ""))
        .strip()
        .casefold()
        in _TRUE
    )


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().casefold()
    return raw in _TRUE


@pytest.fixture(scope="session")
def live_steering_classifier() -> ProviderSemanticIntentClassifier:
    if not _enabled():
        pytest.skip(
            "live Codex steering matrix is opt-in; set "
            "OMNIX_RUN_LIVE_CODEX_STEERING_TESTS=1"
        )

    codex_path = str(os.environ.get("OMNIX_LIVE_CODEX_PATH", "codex") or "codex").strip()
    model = str(
        os.environ.get("OMNIX_LIVE_CODEX_SEMANTIC_MODEL", "gpt-5.6-sol")
        or "gpt-5.6-sol"
    ).strip()
    effort = str(
        os.environ.get("OMNIX_LIVE_CODEX_REASONING_EFFORT", "medium")
        or "medium"
    ).strip()

    status = ChatGPTCodexProvider.auth_status(codex_path)
    if not (
        status.get("installed")
        and status.get("authenticated")
        and status.get("auth_mode") == "chatgpt"
    ):
        pytest.fail(
            "live Codex steering tests were enabled but Codex is not "
            f"ChatGPT-authenticated: {status}"
        )

    provider = ChatGPTCodexProvider(
        ProviderConfig(
            provider_type="chatgpt_codex",
            model=model,
            timeout=90.0,
            extra_params={
                "codex_path": codex_path,
                "reasoning_effort": effort,
                "fast_mode": _bool_env("OMNIX_LIVE_CODEX_FAST_MODE", True),
                "transport": "app_server",
            },
        )
    )
    if not provider.test_connection():
        provider.close()
        pytest.fail("Codex app-server transport could not be initialized")

    classifier = ProviderSemanticIntentClassifier(
        provider,
        model=model,
        timeout_seconds=60.0,
    )
    try:
        yield classifier
    finally:
        provider.close()


@pytest.mark.live_codex
@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_live_codex_steering_matrix(
    live_steering_classifier: ProviderSemanticIntentClassifier,
    case: SteeringCase,
) -> None:
    effective = revise_objective(case.initial, case.steering)
    decision = live_steering_classifier.classify(effective)
    payload = decision.model_dump(mode="json")

    assert decision.confidence >= semantic_confidence_threshold(), payload
    assert decision.lane == case.lane, {
        "effective_objective": effective,
        "decision": payload,
    }

    profile_id = semantic_profile_id(effective, decision)
    assert profile_id == case.profile, {
        "effective_objective": effective,
        "expected_profile": case.profile,
        "actual_profile": profile_id,
        "decision": payload,
    }

    actions = set(decision.action_intents)
    assert set(case.required_actions) <= actions, {
        "missing_actions": sorted(set(case.required_actions) - actions),
        "decision": payload,
    }
    assert not (set(case.forbidden_actions) & actions), {
        "forbidden_actions": sorted(set(case.forbidden_actions) & actions),
        "decision": payload,
    }

    proposal = evidence_decision_from_semantic(effective, decision)
    evidence = classify_evidence(
        effective,
        profile_id=profile_id,
        semantic_adviser=lambda *_: proposal,
    )
    sources = {row.source_class for row in evidence.policy.requirements}
    assert set(case.required_evidence) <= sources, {
        "missing_evidence": sorted(set(case.required_evidence) - sources),
        "effective_evidence": sorted(sources),
        "decision": payload,
    }

    compiled = compile_task_authority(
        get_agent_profile(profile_id),
        effective,
        evidence,
        semantic_action_intents=decision.action_intents,
    )
    local = set(compiled.required_local)
    external = set(compiled.required_external)

    assert set(case.required_local) <= local
    assert not (set(case.forbidden_local) & local)
    assert set(case.required_external) <= external
    assert not (set(case.forbidden_external) & external)


def test_live_steering_matrix_has_multiple_authority_transitions() -> None:
    assert len(CASES) >= 12
    assert sum(bool(case.required_external) for case in CASES) >= 5
    assert sum(bool(case.forbidden_actions) for case in CASES) >= 4
