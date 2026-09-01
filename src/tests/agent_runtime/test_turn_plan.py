from __future__ import annotations

from app.agent_runtime.active_objective import (
    advance_active_objective,
    make_active_objective,
)
from app.agent_runtime.semantic_normalizer import normalize_semantic_task
from app.agent_runtime.semantic_task import (
    SemanticDataDependency,
    SemanticOperation,
    SemanticSubject,
    SemanticTask,
)
from app.agent_runtime.turn_plan import compile_turn_plan


def _task(
    *,
    intent: str = "task",
    operations: list[SemanticOperation] | None = None,
    dependencies: list[SemanticDataDependency] | None = None,
    relation: str = "none",
    request_completeness: str = "self_contained",
    autonomous: bool = False,
    multi_step: bool = False,
    subjects: list[SemanticSubject] | None = None,
) -> SemanticTask:
    return SemanticTask(
        intent=intent,
        operations=list(operations or []),
        data_dependencies=list(dependencies or []),
        objective_relation=relation,
        request_completeness=request_completeness,
        autonomous=autonomous,
        multi_step=multi_step,
        subjects=list(subjects or []),
        ambiguity="none",
        confidence=0.99,
        reason_code="turn_plan_test",
    )


def _active(profile: str = "coding"):
    return make_active_objective(
        canonical_request="Fix the stale assertion.",
        base_request="Diagnose the CI failure.",
        profile=profile,
        status="active",
        run_id="run-1",
    )


def test_response_only_continuation_stays_on_active_agent_boundary() -> None:
    plan = compile_turn_plan(
        "Summarize what you found.",
        _task(
            intent="summarize findings",
            operations=[
                SemanticOperation(
                    kind="explain",
                    target="conversation",
                    subject_reference="prior findings",
                )
            ],
            relation="continue",
        ),
        active_objective=_active("research"),
    )

    assert plan.lane == "agent"
    assert plan.profile_id == "research"
    assert plan.run_action == "steer_agent"
    assert plan.disposition == "response_only_continuation"
    assert plan.authority_delta == []
    assert plan.effective_request == "Summarize what you found."


def test_unrelated_response_only_chat_does_not_inherit_active_agent() -> None:
    plan = compile_turn_plan(
        "Explain TCP congestion control.",
        _task(
            intent="explain TCP congestion control",
            operations=[
                SemanticOperation(
                    kind="explain",
                    target="conversation",
                    subject_reference="TCP congestion control",
                )
            ],
            relation="none",
        ),
        active_objective=_active("research"),
    )

    assert plan.lane == "chat"
    assert plan.run_action == "chat"
    assert plan.disposition == "new_objective"


def test_opaque_resume_replays_latest_user_authored_request() -> None:
    active = advance_active_objective(
        _active(),
        request="Fix the stale assertion and rerun the focused test.",
        profile="coding",
        relation="revise",
        disposition="revise_objective",
        turn_id="turn-2",
        run_id="run-1",
    )
    plan = compile_turn_plan(
        "Try that exact implementation request again.",
        _task(
            intent="retry prior implementation",
            operations=[
                SemanticOperation(
                    kind="modify",
                    target="repository",
                    subject_reference="prior implementation",
                )
            ],
            relation="resume",
            request_completeness="context_dependent",
            autonomous=True,
        ),
        active_objective=active,
        routing_environment={"active_workspace": "omnix"},
    )

    assert plan.relation == "resume"
    assert plan.disposition == "replay_objective"
    assert plan.effective_request == (
        "Fix the stale assertion and rerun the focused test."
    )
    assert plan.run_action == "steer_agent"


def test_complete_retry_command_remains_authoritative() -> None:
    plan = compile_turn_plan(
        "Run the focused test again.",
        _task(
            intent="rerun focused test",
            operations=[
                SemanticOperation(
                    kind="execute",
                    target="repository",
                    subject_reference="focused test",
                )
            ],
            relation="resume",
            autonomous=True,
        ),
        active_objective=_active(),
        routing_environment={"active_workspace": "omnix"},
    )

    assert plan.relation == "resume"
    assert plan.disposition == "continue_objective"
    assert plan.effective_request == "Run the focused test again."
    assert plan.authority_delta == ["workspace_execute"]


def test_selected_local_workspace_satisfies_repo_contents_not_remote_ci() -> None:
    local_plan = compile_turn_plan(
        "Inspect the selected repo.",
        _task(
            intent="inspect repository",
            operations=[
                SemanticOperation(
                    kind="inspect",
                    target="repository",
                    subject_reference="current repository",
                )
            ],
            dependencies=[
                SemanticDataDependency(
                    target="repository",
                    freshness="current",
                    subject_reference="current repository",
                )
            ],
            autonomous=True,
        ),
        routing_environment={"active_workspace": "omnix"},
    )
    assert local_plan.lane == "agent"
    assert (
        local_plan.compilation.evidence_decision.policy.requirements == []
    )

    ci_plan = compile_turn_plan(
        "Inspect the current CI failure.",
        _task(
            intent="inspect current CI",
            operations=[
                SemanticOperation(
                    kind="inspect",
                    target="repository_ci",
                    subject_reference="current repository",
                )
            ],
            dependencies=[
                SemanticDataDependency(
                    target="repository_ci",
                    freshness="current",
                    subject_reference="current repository",
                )
            ],
            autonomous=True,
        ),
        routing_environment={"active_workspace": "omnix"},
    )
    assert {
        requirement.source_class
        for requirement in ci_plan.compilation.evidence_decision.policy.requirements
    } == {"repo_ci_state"}


def test_semantic_normalizer_keeps_topical_explanation_response_only() -> None:
    raw = _task(
        intent="explain filings",
        operations=[
            SemanticOperation(
                kind="explain",
                target="market_filing",
                subject_reference="how filings work",
            ),
            SemanticOperation(
                kind="explain",
                target="market_filing",
                subject_reference="how filings work",
            ),
        ],
        subjects=[
            SemanticSubject(
                target="conversation",
                reference="company filings",
                kind="topic",
            )
        ],
    )

    normalized = normalize_semantic_task(raw)

    assert len(normalized.operations) == 1
    assert normalized.operations[0].target == "conversation"


def test_structured_objective_history_keeps_user_authored_revisions() -> None:
    objective = make_active_objective(
        canonical_request="Inspect the router.",
        profile="coding",
        status="active",
        run_id="run-1",
        originating_turn_id="turn-1",
    )
    objective = advance_active_objective(
        objective,
        request="Run the focused tests.",
        profile="coding",
        relation="continue",
        disposition="continue_objective",
        turn_id="turn-2",
        run_id="run-1",
    )
    objective = advance_active_objective(
        objective,
        request="Fix only the stale assertion.",
        profile="coding",
        relation="revise",
        disposition="revise_objective",
        turn_id="turn-3",
        run_id="run-1",
    )

    assert objective.base_request == "Inspect the router."
    assert [entry.request for entry in objective.revisions] == [
        "Run the focused tests.",
        "Fix only the stale assertion.",
    ]
    assert objective.latest_user_request() == "Fix only the stale assertion."
    assert objective.effective_objective_text() == "Fix only the stale assertion."
