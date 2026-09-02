from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent_runtime.contracts import EvidenceReceipt, SubjectRef
from app.agent_runtime.evidence import compile_task_authority, evaluate_evidence_set
from app.agent_runtime.profiles import get_agent_profile
from app.agent_runtime.router import route_omnix_fast_path
from app.agent_runtime.semantic_normalizer import normalize_semantic_task
from app.agent_runtime.semantic_task import (
    SemanticDataDependency,
    SemanticOperation,
    SemanticSubject,
    SemanticTask,
    compile_semantic_task,
)


def test_semantic_task_contract_cannot_select_profile_or_capabilities() -> None:
    with pytest.raises(ValidationError):
        SemanticTask.model_validate(
            {
                "intent": "fix theme",
                "operations": [{"kind": "modify", "target": "workspace"}],
                "profile_id": "house",
            }
        )


def test_workspace_theme_mutation_compiles_to_coding_without_home_evidence() -> None:
    task = SemanticTask(
        intent="repair Aurora light-mode appearance",
        subjects=[
            SemanticSubject(
                target="workspace",
                reference="Aurora light mode",
                kind="software_ui",
            )
        ],
        operations=[
            SemanticOperation(kind="inspect", target="workspace"),
            SemanticOperation(kind="modify", target="workspace"),
            SemanticOperation(kind="validate", target="workspace"),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
        confidence=0.42,
        reason_code="workspace_ui_mutation",
    )

    compiled = compile_semantic_task(
        "aurora light mode still doesn't look good. can you fix it. applies to all styles.",
        task,
    )

    assert compiled.lane == "agent"
    assert compiled.profile_id == "coding"
    assert compiled.action_intents == [
        "workspace_read",
        "workspace_mutate",
        "workspace_execute",
    ]
    assert compiled.evidence_decision.policy.requirement == "none"
    assert compiled.requires_clarification is False


def test_physical_light_mutation_compiles_to_house_with_current_home_state() -> None:
    task = SemanticTask(
        intent="repair bedroom light",
        subjects=[SemanticSubject(target="home", reference="bedroom light")],
        operations=[SemanticOperation(kind="modify", target="home")],
        autonomous=True,
        reason_code="home_device_mutation",
    )

    compiled = compile_semantic_task("fix the bedroom light; it won't turn on", task)

    assert compiled.lane == "agent"
    assert compiled.profile_id == "house"
    assert compiled.action_intents == ["home_mutate"]
    requirements = compiled.evidence_decision.policy.requirements
    assert [row.source_class for row in requirements] == ["home_state"]
    assert requirements[0].trust_floor == "authoritative"
    assert requirements[0].fallback_policy == "fail_closed"
    assert requirements[0].freshness == "current"


def test_bounded_weather_lookup_stays_chat_but_uses_runtime_evidence_policy() -> None:
    task = SemanticTask(
        intent="check tomorrow weather",
        subjects=[SemanticSubject(target="weather", reference="tomorrow morning")],
        operations=[SemanticOperation(kind="read", target="weather")],
        data_dependencies=[
            SemanticDataDependency(target="weather", freshness="current")
        ],
        autonomous=False,
        multi_step=False,
        reason_code="weather_lookup",
    )

    compiled = compile_semantic_task("what will the weather be like tomorrow morning?", task)

    assert compiled.lane == "chat"
    assert compiled.profile_id == "research"
    requirement = compiled.evidence_decision.policy.requirements[0]
    assert requirement.source_class == "weather_state"
    assert requirement.trust_floor == "authoritative"
    assert requirement.max_age_seconds is not None


def test_weather_subject_uses_resolved_location_subject_when_marked_as_location() -> None:
    task = SemanticTask(
        intent="check weather in Vancouver",
        subjects=[
            SemanticSubject(
                target="weather",
                reference="Vancouver",
                kind="location",
            )
        ],
        operations=[SemanticOperation(kind="read", target="weather")],
        data_dependencies=[
            SemanticDataDependency(target="weather", freshness="current")
        ],
        autonomous=False,
        multi_step=False,
        reason_code="weather_lookup",
    )

    compiled = compile_semantic_task("what will the weather be like there tomorrow?", task)

    requirement = compiled.evidence_decision.policy.requirements[0]
    assert requirement.source_class == "weather_state"
    assert requirement.subject is not None
    assert requirement.subject.type == "location"
    assert requirement.subject.canonical_id == "vancouver"


def test_local_operational_diagnostics_compile_to_ops_with_least_privilege() -> None:
    task = SemanticTask(
        intent="diagnose the local service and run health checks",
        subjects=[
            SemanticSubject(
                target="operations",
                reference="local Omnix service",
                kind="service",
            )
        ],
        operations=[
            SemanticOperation(kind="inspect", target="operations"),
            SemanticOperation(kind="execute", target="operations"),
            SemanticOperation(kind="validate", target="operations"),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
        reason_code="local_ops_diagnostics",
    )

    semantic = compile_semantic_task(
        "diagnose why the local service keeps crashing and run the relevant checks",
        task,
    )

    assert semantic.lane == "agent"
    assert semantic.profile_id == "ops"
    assert semantic.action_intents == ["ops_read", "ops_execute"]
    assert semantic.evidence_decision.policy.requirement == "none"

    authority = compile_task_authority(
        get_agent_profile("ops"),
        "diagnose why the local service keeps crashing and run the relevant checks",
        semantic.evidence_decision,
        semantic_action_intents=semantic.action_intents,
        allow_text_semantic_fallback=False,
    )
    assert "workspace.read" in authority.required_local
    assert "workspace.command" in authority.required_local
    assert "workspace.test" in authority.required_local
    assert "workspace.edit" not in authority.required_local
    assert "workspace.write" not in authority.required_local


def test_open_ended_public_research_becomes_research_agent() -> None:
    task = SemanticTask(
        intent="compare current database releases",
        operations=[SemanticOperation(kind="compare", target="public_web")],
        data_dependencies=[
            SemanticDataDependency(target="public_web", freshness="current")
        ],
        autonomous=True,
        multi_step=True,
        reason_code="open_ended_public_research",
    )

    compiled = compile_semantic_task("compare the latest database releases", task)

    assert compiled.lane == "agent"
    assert compiled.profile_id == "research"
    assert compiled.action_intents == ["research_read"]


def test_timeless_public_research_is_not_forced_into_current_freshness() -> None:
    task = SemanticTask(
        intent="research a historical topic with sources",
        operations=[SemanticOperation(kind="research", target="public_web")],
        autonomous=True,
        multi_step=True,
        reason_code="historical_research",
    )

    compiled = compile_semantic_task("research the history of TCP congestion control", task)

    requirement = compiled.evidence_decision.policy.requirements[0]
    assert requirement.source_class == "general_current_web"
    assert requirement.freshness == "timeless"
    assert requirement.max_age_seconds is None


def test_workspace_create_is_a_workspace_mutation() -> None:
    task = SemanticTask(
        intent="add a regression test",
        operations=[
            SemanticOperation(kind="modify", target="workspace"),
            SemanticOperation(kind="create", target="workspace"),
            SemanticOperation(kind="validate", target="workspace"),
        ],
        autonomous=True,
        multi_step=True,
        reason_code="workspace_change_with_new_test",
    )

    compiled = compile_semantic_task(
        "Apply the UI change and add a regression test.",
        task,
    )

    assert compiled.lane == "agent"
    assert compiled.profile_id == "coding"
    assert set(compiled.action_intents) == {
        "workspace_mutate",
        "workspace_execute",
    }
    assert compiled.requires_clarification is False
    assert "create:workspace" not in compiled.denied_actions


def test_multi_company_filing_research_is_open_ended_discovery() -> None:
    task = SemanticTask(
        intent="compare material filings for NVDA and AMD",
        subjects=[
            SemanticSubject(target="market_filing", reference="NVDA", kind="company"),
            SemanticSubject(target="market_filing", reference="AMD", kind="company"),
        ],
        operations=[
            SemanticOperation(
                kind="research",
                target="market_filing",
                subject_reference="filings that materially change the NVDA versus AMD comparison",
            ),
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="market_filing",
                freshness="current",
                subject_reference="filings that materially change the NVDA versus AMD comparison",
            ),
        ],
        autonomous=True,
        multi_step=True,
        reason_code="multi_company_filing_discovery",
    )

    compiled = compile_semantic_task(
        "Include any company filing from this week that materially changes the comparison.",
        task,
    )

    assert compiled.lane == "agent"
    assert compiled.profile_id == "trading-research"
    assert compiled.action_intents == ["market_read"]
    assert compiled.requires_clarification is False
    assert not any(
        anomaly.code == "unresolved_evidence_subject"
        for anomaly in compiled.anomalies
    )


def test_market_plus_public_research_compiles_to_trading_research_profile() -> None:
    task = SemanticTask(
        intent="research a stock using quote and public sources",
        subjects=[
            SemanticSubject(target="market", reference="GME", kind="security"),
        ],
        operations=[
            SemanticOperation(kind="read", target="market_quote", subject_reference="GME"),
            SemanticOperation(kind="research", target="public_web"),
        ],
        autonomous=True,
        multi_step=True,
        reason_code="market_research",
    )

    compiled = compile_semantic_task("research GME and check its current quote", task)

    assert compiled.profile_id == "trading-research"
    assert compiled.requires_clarification is False
    assert set(compiled.action_intents) == {"market_read", "research_read"}


def test_dynamic_market_screen_can_compare_unresolved_candidate_quotes() -> None:
    task = SemanticTask(
        intent="narrow today's volatile gainers by liquidity and volume",
        subjects=[
            SemanticSubject(
                target="market_status",
                reference="today's volatile US gainers",
                kind="candidate_list",
            ),
        ],
        operations=[
            SemanticOperation(
                kind="research",
                target="market_status",
                subject_reference="today's volatile US gainers",
            ),
            SemanticOperation(
                kind="compare",
                target="market_quote",
                subject_reference="current volume and liquidity for the researched candidates",
            ),
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="market_status",
                freshness="current",
                subject_reference="today's volatile US gainers",
            ),
            SemanticDataDependency(
                target="market_quote",
                freshness="current",
                subject_reference="current volume and liquidity for the researched candidates",
            ),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="resolvable_from_context",
        reason_code="refine_market_research_screen",
    )

    compiled = compile_semantic_task(
        "Narrow the list to names with sufficient liquidity and meaningful current volume.",
        task,
    )

    assert compiled.lane == "agent"
    assert compiled.profile_id == "trading-research"
    assert compiled.action_intents == ["market_read"]
    assert compiled.requires_clarification is False
    assert "market_quote" not in compiled.denied_actions
    assert not any(
        anomaly.code == "unresolved_evidence_subject"
        for anomaly in compiled.anomalies
    )


def test_ambiguity_is_a_gate_not_a_confidence_threshold() -> None:
    low_confidence_unambiguous = SemanticTask(
        intent="fix workspace",
        operations=[SemanticOperation(kind="modify", target="workspace")],
        autonomous=True,
        ambiguity="none",
        confidence=0.12,
        reason_code="workspace_mutation",
    )
    compiled = compile_semantic_task("fix it", low_confidence_unambiguous)
    assert compiled.lane == "agent"
    assert compiled.requires_clarification is False

    ambiguous = low_confidence_unambiguous.model_copy(
        update={
            "ambiguity": "clarification_required",
            "candidate_interpretations": ["workspace issue", "bedroom light"],
        }
    )
    blocked = compile_semantic_task("fix it", ambiguous)
    assert blocked.lane == "chat"
    assert blocked.requires_clarification is True


def test_cross_profile_composite_is_detected_instead_of_silently_widened() -> None:
    task = SemanticTask(
        intent="fix code then email Sarah",
        operations=[
            SemanticOperation(kind="modify", target="workspace"),
            SemanticOperation(kind="send", target="email"),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
        reason_code="cross_domain_composite",
    )

    compiled = compile_semantic_task("fix it and email Sarah when done", task)

    assert compiled.requires_clarification is True
    assert compiled.profile_id is None
    assert any(
        row.code == "unsupported_composite_profiles"
        for row in compiled.anomalies
    )


def test_subject_operation_disagreement_is_visible_and_fail_closed() -> None:
    task = SemanticTask(
        intent="fix CSS",
        subjects=[SemanticSubject(target="workspace", reference="CSS")],
        operations=[SemanticOperation(kind="send", target="email")],
        autonomous=True,
        ambiguity="none",
        reason_code="bad_cross_domain_output",
    )

    compiled = compile_semantic_task("fix the CSS", task)

    assert compiled.requires_clarification is True
    assert any(
        row.code == "unexpected_cross_domain_action"
        and row.rejected_operation == "email_send"
        for row in compiled.anomalies
    )


def test_context_resolved_market_subject_is_bound_to_evidence_and_wrong_subject_fails() -> None:
    task = SemanticTask(
        intent="check how GME is trading",
        subjects=[SemanticSubject(target="market_quote", reference="GME")],
        operations=[
            SemanticOperation(
                kind="read",
                target="market_quote",
                subject_reference="GME",
            )
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="market_quote",
                freshness="current",
                subject_reference="GME",
            )
        ],
        autonomous=False,
        reason_code="contextual_market_quote",
    )

    compiled = compile_semantic_task("what about it?", task)
    requirement = compiled.evidence_decision.policy.requirements[0]
    assert requirement.subject is not None
    assert requirement.subject.qualifiers["ticker"] == "GME"

    wrong = EvidenceReceipt(
        receipt_id="wrong-security",
        run_id="contextual-market",
        capability_id="trading.market_quote",
        source_class="market_quote",
        subject=SubjectRef(
            type="security",
            canonical_id="NVDA",
            display_name="NVDA",
            qualifiers={"ticker": "NVDA"},
        ),
        request_digest="request",
        source_count=1,
        trust_level="authoritative",
        result_digest="result",
    )
    evidence = evaluate_evidence_set(
        "contextual-market",
        compiled.evidence_decision.policy,
        [wrong],
    )
    assert evidence.passed is False
    assert evidence.wrong_subject_receipts == ["wrong-security"]


def test_unsupported_semantic_operation_fails_closed_and_is_reported_denied() -> None:
    task = SemanticTask(
        intent="unsupported workspace send",
        subjects=[SemanticSubject(target="workspace", reference="current workspace")],
        operations=[SemanticOperation(kind="send", target="workspace")],
        autonomous=True,
        ambiguity="none",
        reason_code="unsupported_workspace_operation",
    )

    compiled = compile_semantic_task("send the workspace", task)

    assert compiled.lane == "chat"
    assert compiled.requires_clarification is True
    assert "send:workspace" in compiled.denied_actions
    assert any(
        anomaly.code == "unsupported_semantic_operation"
        for anomaly in compiled.anomalies
    )


def test_repository_ci_evidence_policy_is_compiler_owned() -> None:
    task = SemanticTask(
        intent="inspect current CI",
        operations=[SemanticOperation(kind="inspect", target="repository_ci")],
        data_dependencies=[
            SemanticDataDependency(target="repository_ci", freshness="current")
        ],
        autonomous=True,
        reason_code="repository_ci_inspection",
    )

    compiled = compile_semantic_task("check whether CI is red", task)

    assert compiled.profile_id == "coding"
    assert compiled.action_intents == ["repo_ci_read"]
    requirement = compiled.evidence_decision.policy.requirements[0]
    assert requirement.source_class == "repo_ci_state"
    assert requirement.trust_floor == "authoritative"
    assert requirement.fallback_policy == "fail_closed"
    assert requirement.max_age_seconds is not None


def test_email_send_does_not_grant_inbox_read_without_dependency() -> None:
    task = SemanticTask(
        intent="send a status email",
        operations=[SemanticOperation(kind="send", target="email")],
        autonomous=True,
        reason_code="email_send",
    )
    semantic = compile_semantic_task("email Alex that I'm running late", task)
    compiled = compile_task_authority(
        get_agent_profile("personal-assistant"),
        "email Alex that I'm running late",
        semantic.evidence_decision,
        semantic_action_intents=semantic.action_intents,
        allow_text_semantic_fallback=False,
    )

    assert "gmail.send_email" in compiled.required_external
    assert "gmail.read_email" not in compiled.required_external


def test_calendar_create_does_not_grant_availability_read_without_dependency() -> None:
    task = SemanticTask(
        intent="create a calendar event at an explicit time",
        operations=[SemanticOperation(kind="create", target="calendar")],
        autonomous=True,
        reason_code="calendar_create",
    )
    semantic = compile_semantic_task("schedule lunch tomorrow at noon", task)
    compiled = compile_task_authority(
        get_agent_profile("personal-assistant"),
        "schedule lunch tomorrow at noon",
        semantic.evidence_decision,
        semantic_action_intents=semantic.action_intents,
        allow_text_semantic_fallback=False,
    )

    assert "calendar.create_event" in compiled.required_external
    assert "calendar.read_availability" not in compiled.required_external


def test_syntax_fast_path_does_not_classify_natural_language_domains() -> None:
    assert route_omnix_fast_path("/agent fix it").reason == "explicit_agent"
    assert route_omnix_fast_path("turn off the desk light").lane == "direct"

    semantic = route_omnix_fast_path(
        "aurora light mode still doesn't look good. can you fix it."
    )
    assert semantic.lane == "chat"
    assert semantic.reason == "semantic_required"

    home_semantic = route_omnix_fast_path("fix the bedroom light; it won't turn on")
    assert home_semantic.lane == "chat"
    assert home_semantic.reason == "semantic_required"


def test_bounded_public_lookup_stays_chat_even_if_model_marks_autonomous() -> None:
    task = SemanticTask(
        intent="check current NVDA quote",
        subjects=[SemanticSubject(target="market_quote", reference="NVDA")],
        operations=[
            SemanticOperation(
                kind="read",
                target="market_quote",
                subject_reference="NVDA",
            )
        ],
        autonomous=True,
        multi_step=False,
        reason_code="bounded_quote_lookup",
    )

    compiled = compile_semantic_task("check the current NVDA quote", task)

    assert compiled.lane == "chat"
    assert compiled.profile_id == "trading-research"
    assert compiled.action_intents == ["market_read"]
    assert compiled.requires_clarification is False


def test_explanation_targeted_at_stateful_domain_is_response_only() -> None:
    task = SemanticTask(
        intent="explain smart plug state versus toggling",
        subjects=[SemanticSubject(target="home", reference="smart plug")],
        operations=[SemanticOperation(kind="explain", target="home")],
        autonomous=False,
        multi_step=False,
        reason_code="conceptual_home_explanation",
    )

    compiled = compile_semantic_task(
        "what is the difference between checking a smart plug state and toggling it?",
        task,
    )

    assert compiled.lane == "chat"
    assert compiled.action_intents == []
    assert compiled.requires_clarification is False


def test_home_mutation_validation_compiles_to_mutate_plus_readback() -> None:
    task = SemanticTask(
        intent="turn off and verify hallway light",
        subjects=[SemanticSubject(target="home", reference="hallway light")],
        operations=[
            SemanticOperation(kind="modify", target="home"),
            SemanticOperation(kind="validate", target="home"),
        ],
        autonomous=True,
        multi_step=True,
        reason_code="home_mutate_verify",
    )

    compiled = compile_semantic_task(
        "turn that hallway light off and verify it",
        task,
    )

    assert compiled.lane == "agent"
    assert compiled.profile_id == "house"
    assert compiled.action_intents == ["home_mutate", "home_read"]
    assert compiled.requires_clarification is False


def test_all_conversation_verbs_remain_response_only() -> None:
    task = SemanticTask(
        intent="reason about prior conversation without acting",
        subjects=[
            SemanticSubject(
                target="conversation",
                reference="prior discussion",
            )
        ],
        operations=[
            SemanticOperation(kind="research", target="conversation"),
            SemanticOperation(kind="validate", target="conversation"),
            SemanticOperation(kind="modify", target="conversation"),
        ],
        autonomous=False,
        multi_step=False,
        ambiguity="none",
        reason_code="conversation_only",
    )

    compiled = compile_semantic_task(
        "based only on our conversation, reconsider and tighten that explanation",
        task,
    )

    assert compiled.lane == "chat"
    assert compiled.profile_id is None
    assert compiled.action_intents == []
    assert compiled.requires_clarification is False
    assert compiled.anomalies == []


def test_bounded_public_lookup_stays_chat_when_parser_uses_research_verb() -> None:
    task = SemanticTask(
        intent="check current public outage state",
        subjects=[
            SemanticSubject(
                target="public_web",
                reference="GitHub status",
            )
        ],
        operations=[
            SemanticOperation(
                kind="research",
                target="public_web",
                subject_reference="GitHub status",
            )
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="public_web",
                freshness="current",
                subject_reference="GitHub status",
            )
        ],
        autonomous=True,
        multi_step=False,
        ambiguity="none",
        reason_code="bounded_status_lookup",
    )

    compiled = compile_semantic_task(
        "check whether GitHub is reporting a public outage right now",
        task,
    )

    assert compiled.lane == "chat"
    assert compiled.profile_id == "research"
    assert compiled.action_intents == ["research_read"]
    assert compiled.requires_clarification is False


def test_open_ended_public_research_stays_agent_when_multi_step() -> None:
    task = SemanticTask(
        intent="research current incident scope and recovery",
        subjects=[
            SemanticSubject(
                target="public_web",
                reference="GitHub incident",
            )
        ],
        operations=[
            SemanticOperation(kind="research", target="public_web"),
            SemanticOperation(kind="compare", target="public_web"),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
        reason_code="incident_research",
    )

    compiled = compile_semantic_task(
        "research the incident, affected services, timeline, and recovery updates",
        task,
    )

    assert compiled.lane == "agent"
    assert compiled.profile_id == "research"
    assert compiled.action_intents == ["research_read"]
    assert compiled.requires_clarification is False


def test_home_energy_research_maps_to_read_only_house_authority() -> None:
    task = SemanticTask(
        intent="identify the largest current home energy load",
        subjects=[
            SemanticSubject(
                target="home_energy",
                reference="current home",
            )
        ],
        operations=[
            SemanticOperation(kind="research", target="home_energy"),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
        reason_code="home_energy_research",
    )

    compiled = compile_semantic_task(
        "check today's available energy telemetry and identify the largest load",
        task,
    )

    assert compiled.lane == "agent"
    assert compiled.profile_id == "house"
    assert compiled.action_intents == ["home_read"]
    assert compiled.requires_clarification is False
    assert [
        requirement.source_class
        for requirement in compiled.evidence_decision.policy.requirements
    ] == ["home_energy"]


def test_public_service_status_is_not_repository_ci() -> None:
    task = SemanticTask(
        intent="continue researching the public service incident",
        subjects=[
            SemanticSubject(
                target="repository_ci",
                reference="GitHub's current public service incident",
                kind="incident",
            ),
            SemanticSubject(
                target="public_web",
                reference="broader reports about the same incident",
                kind="incident",
            ),
        ],
        operations=[
            SemanticOperation(
                kind="research",
                target="repository_ci",
                subject_reference="GitHub's current public service incident",
            ),
            SemanticOperation(
                kind="research",
                target="public_web",
                subject_reference="broader reports about the same incident",
            ),
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="repository_ci",
                freshness="current",
                subject_reference="GitHub's current public service incident",
                retrieval_mode="discover",
            ),
            SemanticDataDependency(
                target="public_web",
                freshness="current",
                subject_reference="broader reports about the same incident",
                retrieval_mode="discover",
            ),
        ],
        objective_relation="continue",
        reason_code="public_service_status_test",
    )

    normalized = normalize_semantic_task(task)

    assert {subject.target for subject in normalized.subjects} == {"public_web"}
    assert {operation.target for operation in normalized.operations} == {"public_web"}
    assert {dependency.target for dependency in normalized.data_dependencies} == {
        "public_web"
    }


def test_repository_ci_research_verbs_remain_read_only_coding_inspection() -> None:
    task = SemanticTask(
        intent="compare current CI failures",
        subjects=[
            SemanticSubject(
                target="repository_ci",
                reference="current repository CI",
            )
        ],
        operations=[
            SemanticOperation(kind="research", target="repository_ci"),
            SemanticOperation(kind="compare", target="repository_ci"),
            SemanticOperation(kind="validate", target="repository_ci"),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
        reason_code="ci_research",
    )

    compiled = compile_semantic_task(
        "research the current CI failures and compare the failing checks",
        task,
    )

    assert compiled.lane == "agent"
    assert compiled.profile_id == "coding"
    assert compiled.action_intents == ["repo_ci_read"]
    assert compiled.requires_clarification is False
    assert [
        requirement.source_class
        for requirement in compiled.evidence_decision.policy.requirements
    ] == ["repo_ci_state"]


def test_validate_only_repository_ci_still_requires_current_ci_evidence() -> None:
    task = SemanticTask(
        intent="validate current CI state",
        subjects=[
            SemanticSubject(
                target="repository_ci",
                reference="current repository CI",
            )
        ],
        operations=[
            SemanticOperation(kind="validate", target="repository_ci"),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
        reason_code="ci_validation",
    )

    compiled = compile_semantic_task(
        "validate the current CI state before we continue",
        task,
    )

    assert compiled.lane == "agent"
    assert compiled.profile_id == "coding"
    assert compiled.action_intents == ["repo_ci_read"]
    assert [
        requirement.source_class
        for requirement in compiled.evidence_decision.policy.requirements
    ] == ["repo_ci_state"]


def test_dynamic_market_discovery_can_bind_quote_subject_during_agent_research() -> None:
    task = SemanticTask(
        intent="research volatile gainers then quote candidates",
        operations=[
            SemanticOperation(kind="research", target="market"),
            SemanticOperation(kind="research", target="public_web"),
            SemanticOperation(kind="read", target="market_quote"),
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="market_quote",
                freshness="current",
                subject_reference=None,
            )
        ],
        autonomous=True,
        multi_step=True,
        reason_code="dynamic_market_discovery",
    )

    compiled = compile_semantic_task(
        "research today's volatile gainers and check current quotes for the best candidates",
        task,
    )

    assert compiled.lane == "agent"
    assert compiled.profile_id == "trading-research"
    assert compiled.requires_clarification is False
    assert not any(
        anomaly.code == "unresolved_evidence_subject"
        for anomaly in compiled.anomalies
    )
