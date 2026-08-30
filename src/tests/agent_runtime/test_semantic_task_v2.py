from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent_runtime.evidence import compile_task_authority
from app.agent_runtime.profiles import get_agent_profile
from app.agent_runtime.router import route_omnix_fast_path
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
    assert compiled.action_intents == ["workspace_execute"]
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
