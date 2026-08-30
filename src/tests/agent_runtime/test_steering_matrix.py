from __future__ import annotations

from app.agent_runtime.contracts import (
    AgentArtifact,
    AgentEvent,
    EvidenceReceipt,
    TaskRevision,
)
from app.agent_runtime.evidence import (
    classify_evidence,
    compile_task_authority,
    evaluate_evidence_set,
    revise_objective,
    steering_semantic_context,
)
from app.agent_runtime.profiles import get_agent_profile
from app.agent_runtime.service import AgentRunService


def _compile(profile_id: str, objective: str, *, actions=()):
    decision = classify_evidence(objective, profile_id=profile_id)
    compiled = compile_task_authority(
        get_agent_profile(profile_id),
        objective,
        decision,
        semantic_action_intents=actions,
    )
    return decision, compiled


def test_steering_replaces_objective_for_explicit_correction() -> None:
    assert revise_objective(
        "Research the latest Python release",
        "Actually explain it from memory only",
    ) == "Actually explain it from memory only"


def test_replacement_steering_keeps_old_task_out_of_effective_authority() -> None:
    effective = revise_objective(
        "Send Bob a status update.",
        "Actually don't send anything; draft the status reply for me to review.",
    )
    assert effective == (
        "Actually don't send anything; draft the status reply for me to review."
    )
    assert "Send Bob" not in effective


def test_steering_semantic_context_preserves_referents_without_authority() -> None:
    context = steering_semantic_context(
        "Send Bob a status update.",
        "Actually don't send anything; draft the status reply for me to review.",
    )
    assert "Previous task context (non-authoritative; reference resolution only):" in context
    assert "Send Bob a status update." in context
    assert "Latest user steering (authoritative; overrides conflicting prior instructions):" in context
    assert "don't send anything; draft the status reply" in context
    assert "Never carry forward an action" in context


def test_steering_appends_incremental_instruction() -> None:
    revised = revise_objective(
        "Inspect the auth tests",
        "also check the retry path",
    )
    assert revised == "Inspect the auth tests\nLater steering: also check the retry path"


def test_steering_can_remove_external_evidence_requirement() -> None:
    original, original_compiled = _compile(
        "research",
        "Research the latest PostgreSQL release",
    )
    assert original.policy.requirement == "required"
    assert "research.web_search" in original_compiled.required_external

    revised = revise_objective(
        "Research the latest PostgreSQL release",
        "Actually explain PostgreSQL releases from memory only",
    )
    decision, compiled = _compile("research", revised)
    assert decision.policy.external_access == "forbidden"
    assert decision.policy.requirement == "none"
    assert compiled.required_external == ()


def test_steering_can_expand_read_only_coding_into_mutation() -> None:
    _, initial = _compile(
        "coding",
        "Inspect the parser code and explain the likely bug",
        actions=("workspace_read",),
    )
    assert "workspace.edit" not in initial.required_local

    revised = revise_objective(
        "Inspect the parser code and explain the likely bug",
        "Actually fix the parser bug in the repo and run the tests",
    )
    _, compiled = _compile(
        "coding",
        revised,
        actions=("workspace_mutate", "workspace_execute"),
    )
    assert "workspace.edit" in compiled.required_local
    assert "workspace.test" in compiled.required_local


def test_steering_can_narrow_coding_back_to_read_only() -> None:
    revised = revise_objective(
        "Fix the failing parser tests",
        "Don't change anything; inspect the parser and explain the failure",
    )
    _, compiled = _compile(
        "coding",
        revised,
        actions=("workspace_read",),
    )
    assert "workspace.read" in compiled.required_local
    assert "workspace.edit" not in compiled.required_local
    assert "workspace.write" not in compiled.required_local


def test_steering_can_upgrade_email_draft_to_send_authority() -> None:
    _, draft = _compile(
        "personal-assistant",
        "Draft an email to Bob about the status update",
        actions=("email_draft",),
    )
    assert "gmail.create_draft" in draft.required_external
    assert "gmail.send_email" not in draft.required_external

    revised = revise_objective(
        "Draft an email to Bob about the status update",
        "Actually send the status email to Bob",
    )
    _, sent = _compile(
        "personal-assistant",
        revised,
        actions=("email_send",),
    )
    assert "gmail.send_email" in sent.required_external


def test_steering_can_narrow_email_send_back_to_draft_only() -> None:
    revised = revise_objective(
        "Send Bob the status update",
        "Actually don't send anything; just draft the reply for review",
    )
    _, compiled = _compile(
        "personal-assistant",
        revised,
        actions=("email_draft",),
    )
    assert "gmail.create_draft" in compiled.required_external
    assert "gmail.send_email" not in compiled.required_external


def test_steering_recompiles_home_state_and_mutation_authority() -> None:
    _, initial = _compile(
        "house",
        "Check whether the bedroom lamp is on",
        actions=("home_read",),
    )
    assert "home.get_state" in initial.required_external
    assert "home.set_state" not in initial.required_external

    revised = revise_objective(
        "Check whether the bedroom lamp is on",
        "Actually turn the bedroom lamp off",
    )
    _, compiled = _compile(
        "house",
        revised,
        actions=("home_mutate",),
    )
    assert "home.get_state" in compiled.required_external
    assert "home.set_state" in compiled.required_external


def test_latest_revision_evidence_does_not_reuse_prior_receipts() -> None:
    revision = TaskRevision(
        run_id="run-1",
        sequence=2,
        user_instruction="Actually research AMD instead",
        effective_objective="Research AMD today",
    )
    prior = EvidenceReceipt(
        run_id="run-1",
        task_revision_id="old-revision",
        capability_id="research.web_search",
        source_class="general_current_web",
        request_digest="old",
        result_digest="old",
    )
    current = prior.model_copy(
        update={
            "receipt_id": "current",
            "task_revision_id": revision.revision_id,
            "request_digest": "new",
            "result_digest": "new",
        }
    )
    assert AgentRunService._receipts_for_revision([prior, current], revision) == [current]


def test_latest_revision_events_do_not_reuse_prior_tool_results() -> None:
    revision = TaskRevision(
        run_id="run-1",
        sequence=2,
        user_instruction="new objective",
        effective_objective="new objective",
    )
    old = AgentEvent(
        run_id="run-1",
        event_type="tool.completed",
        payload={"task_revision_id": "old-revision", "tool_call_id": "old"},
    )
    current = AgentEvent(
        run_id="run-1",
        event_type="tool.completed",
        payload={"task_revision_id": revision.revision_id, "tool_call_id": "new"},
    )
    assert AgentRunService._events_for_revision([old, current], revision) == [current]


def test_latest_revision_artifacts_do_not_reuse_prior_diff() -> None:
    revision = TaskRevision(
        run_id="run-1",
        sequence=2,
        user_instruction="new objective",
        effective_objective="new objective",
    )
    old = AgentArtifact(
        run_id="run-1",
        kind="diff",
        name="old.diff",
        metadata={"task_revision_id": "old-revision"},
    )
    current = AgentArtifact(
        run_id="run-1",
        kind="diff",
        name="new.diff",
        metadata={"task_revision_id": revision.revision_id},
    )
    assert AgentRunService._artifacts_for_revision([old, current], revision) == [current]


def test_revision_policy_is_evaluated_independently() -> None:
    decision = classify_evidence(
        "What is NVDA trading at right now?",
        profile_id="trading-research",
    )
    evidence = evaluate_evidence_set("run-1", decision.policy, [])
    assert evidence.passed is False
    assert evidence.missing_requirements


def test_ambiguous_go_ahead_does_not_remove_prior_read_only_restriction() -> None:
    objective = revise_objective(
        "Inspect the auth code but don't edit anything",
        "go ahead",
    )
    _, compiled = _compile(
        "coding",
        objective,
        actions=("workspace_read",),
    )
    assert "workspace.read" in compiled.required_local
    assert "workspace.edit" not in compiled.required_local
    assert "workspace.write" not in compiled.required_local
