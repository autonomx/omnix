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
from app.agent_runtime.turn_plan import compile_turn_plan, derive_effective_objective


def _task(
    *,
    intent: str = "task",
    operations: list[SemanticOperation] | None = None,
    dependencies: list[SemanticDataDependency] | None = None,
    relation: str = "none",
    request_completeness: str = "self_contained",
    replay_target: str = "latest_authoritative",
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
        replay_target=replay_target,
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


def test_bounded_evidence_continuation_stays_on_chat_scheduler() -> None:
    plan = compile_turn_plan(
        "Add citations for the current claims.",
        _task(
            intent="verify current claims",
            operations=[
                SemanticOperation(
                    kind="compose",
                    target="conversation",
                    subject_reference="prior recommendations",
                )
            ],
            dependencies=[
                SemanticDataDependency(
                    target="public_web",
                    freshness="current",
                    subject_reference="current authoritative documentation",
                    retrieval_mode="verify",
                )
            ],
            relation="continue",
        ),
        active_objective=_active("research"),
    )

    assert plan.lane == "chat"
    assert plan.profile_id == "research"
    assert plan.run_action == "chat"
    assert plan.disposition == "continue_objective"
    assert plan.compilation.retrieval_modes == ["verify"]
    assert plan.compilation.evidence_decision.policy.requirement == "required"


def test_forced_agent_mode_is_compiled_into_final_turn_plan() -> None:
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
        ),
        force_agent=True,
    )

    assert plan.lane == "agent"
    assert plan.profile_id == "research"
    assert plan.run_action == "start_agent"
    assert plan.compilation.lane == "agent"
    assert plan.compilation.profile_id == "research"


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


def test_opaque_resume_can_target_base_objective_explicitly() -> None:
    active = make_active_objective(
        canonical_request="Run the relevant tests and typecheck without further edits.",
        base_request=(
            "Implement the header layout: keep the mode selector, voice selector, "
            "and New Chat visible while reducing crowding."
        ),
        profile="coding",
        status="active",
        run_id="run-1",
    )
    active = advance_active_objective(
        active,
        request="Run the relevant tests and typecheck without further edits.",
        profile="coding",
        relation="continue",
        disposition="continue_objective",
        turn_id="turn-8",
        run_id="run-1",
    )

    plan = compile_turn_plan(
        "Try that exact implementation request again.",
        _task(
            intent="retry original implementation request",
            operations=[
                SemanticOperation(
                    kind="modify",
                    target="repository",
                    subject_reference="original header implementation",
                )
            ],
            relation="resume",
            request_completeness="context_dependent",
            replay_target="base_objective",
            autonomous=True,
        ),
        active_objective=active,
        routing_environment={"active_workspace": "omnix"},
    )

    assert plan.disposition == "replay_objective"
    assert plan.effective_request == (
        "Implement the header layout: keep the mode selector, voice selector, "
        "and New Chat visible while reducing crowding."
    )
    assert plan.authority_delta == ["workspace_mutate"]


def test_context_dependent_mislabel_cannot_replay_complete_retry_command() -> None:
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
            request_completeness="context_dependent",
            autonomous=True,
        ),
        active_objective=_active(),
        routing_environment={"active_workspace": "omnix"},
    )

    assert plan.relation == "resume"
    assert plan.disposition == "continue_objective"
    assert plan.effective_request == "Run the focused test again."
    assert plan.authority_delta == ["workspace_execute"]


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


def test_bounded_external_retrieval_shape_ignores_multi_step_noise() -> None:
    for mode in ("lookup", "verify", "filter"):
        plan = compile_turn_plan(
            "Use the bounded current evidence.",
            _task(
                intent=f"bounded {mode}",
                operations=[
                    SemanticOperation(
                        kind="research",
                        target="public_web",
                        subject_reference="known claims",
                    )
                ],
                dependencies=[
                    SemanticDataDependency(
                        target="public_web",
                        freshness="current",
                        subject_reference="known claims",
                        retrieval_mode=mode,
                    )
                ],
                autonomous=True,
                multi_step=True,
            ),
        )

        assert plan.lane == "chat"
        assert plan.run_action == "chat"
        assert plan.profile_id == "research"
        assert plan.compilation.retrieval_modes == [mode]


def test_discovery_retrieval_shape_routes_agent_without_multi_step_hint() -> None:
    plan = compile_turn_plan(
        "Find whether any matching changes occurred.",
        _task(
            intent="discover matching changes",
            operations=[
                SemanticOperation(
                    kind="read",
                    target="public_web",
                    subject_reference="matching changes",
                )
            ],
            dependencies=[
                SemanticDataDependency(
                    target="public_web",
                    freshness="current",
                    subject_reference="matching changes",
                    retrieval_mode="discover",
                )
            ],
            autonomous=False,
            multi_step=False,
        ),
    )

    assert plan.lane == "agent"
    assert plan.run_action == "start_agent"
    assert plan.profile_id == "research"
    assert plan.compilation.retrieval_modes == ["discover"]


def test_dependency_only_external_read_derives_profile_and_evidence() -> None:
    plan = compile_turn_plan(
        "Finish the recommendation with current sources.",
        _task(
            intent="finish recommendation",
            operations=[
                SemanticOperation(
                    kind="compose",
                    target="conversation",
                    subject_reference="recommendation",
                )
            ],
            dependencies=[
                SemanticDataDependency(
                    target="software_release",
                    freshness="current",
                    subject_reference="known runtime release facts",
                    retrieval_mode="verify",
                )
            ],
        ),
    )

    assert plan.lane == "chat"
    assert plan.profile_id == "research"
    assert plan.authority_delta == []
    assert plan.compilation.retrieval_modes == ["verify"]
    assert {
        requirement.source_class
        for requirement in plan.compilation.evidence_decision.policy.requirements
    } == {"software_release"}


def test_remote_ci_read_is_distinct_from_local_workspace_execution() -> None:
    plan = compile_turn_plan(
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
                    retrieval_mode="lookup",
                )
            ],
        ),
        routing_environment={"active_workspace": "omnix"},
    )

    assert plan.lane == "agent"
    assert plan.profile_id == "coding"
    assert plan.authority_delta == ["repo_ci_read"]
    assert "workspace_execute" not in plan.authority_delta
    assert {
        requirement.source_class
        for requirement in plan.compilation.evidence_decision.policy.requirements
    } == {"repo_ci_state"}


def test_semantic_normalizer_keeps_widest_duplicate_retrieval_scope() -> None:
    raw = _task(
        intent="check and discover changes",
        dependencies=[
            SemanticDataDependency(
                target="public_web",
                freshness="current",
                subject_reference="release changes",
                retrieval_mode="verify",
            ),
            SemanticDataDependency(
                target="public_web",
                freshness="timeless",
                subject_reference="release changes",
                retrieval_mode="discover",
            ),
        ],
    )

    normalized = normalize_semantic_task(raw)

    assert len(normalized.data_dependencies) == 1
    dependency = normalized.data_dependencies[0]
    assert dependency.freshness == "current"
    assert dependency.retrieval_mode == "discover"


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


def test_semantic_normalizer_retargets_explicit_nonsoftware_release() -> None:
    raw = _task(
        intent="research a game release update",
        operations=[
            SemanticOperation(
                kind="research",
                target="software_release",
                subject_reference="current release-date announcements",
            )
        ],
        dependencies=[
            SemanticDataDependency(
                target="software_release",
                freshness="current",
                subject_reference="current release-date announcements",
            )
        ],
        subjects=[
            SemanticSubject(
                target="software_release",
                reference="Example Game",
                kind="game release",
            )
        ],
        autonomous=True,
        multi_step=True,
    )

    normalized = normalize_semantic_task(raw)

    assert [operation.target for operation in normalized.operations] == ["public_web"]
    assert [dependency.target for dependency in normalized.data_dependencies] == ["public_web"]
    assert [subject.target for subject in normalized.subjects] == ["public_web"]


def test_semantic_normalizer_keeps_real_software_release_target() -> None:
    raw = _task(
        intent="research a framework release",
        operations=[
            SemanticOperation(
                kind="research",
                target="software_release",
                subject_reference="latest stable framework release",
            )
        ],
        dependencies=[
            SemanticDataDependency(
                target="software_release",
                freshness="current",
                subject_reference="latest stable framework release",
            )
        ],
        subjects=[
            SemanticSubject(
                target="software_release",
                reference="Example Framework",
                kind="framework",
            )
        ],
        autonomous=True,
        multi_step=True,
    )

    normalized = normalize_semantic_task(raw)

    assert [operation.target for operation in normalized.operations] == ["software_release"]
    assert [dependency.target for dependency in normalized.data_dependencies] == ["software_release"]
    assert [subject.target for subject in normalized.subjects] == ["software_release"]


def test_response_only_revision_does_not_replace_replay_authority() -> None:
    objective = make_active_objective(
        canonical_request="Research the current incident.",
        profile="research",
        status="active",
        run_id="run-1",
    )
    objective = advance_active_objective(
        objective,
        request="Prioritize the provider's own status page.",
        profile="research",
        relation="continue",
        disposition="continue_objective",
        turn_id="turn-2",
        run_id="run-1",
    )
    objective = advance_active_objective(
        objective,
        request="Summarize what you found.",
        profile="research",
        relation="continue",
        disposition="response_only_continuation",
        turn_id="turn-3",
        run_id="run-1",
    )

    assert objective.latest_user_request() == (
        "Prioritize the provider's own status page."
    )
    assert "Summarize what you found." not in objective.effective_objective_text()

    replay = compile_turn_plan(
        "Try that exact request again.",
        _task(
            intent="retry prior research instruction",
            operations=[
                SemanticOperation(
                    kind="research",
                    target="public_web",
                    subject_reference="prior incident",
                )
            ],
            relation="resume",
            request_completeness="context_dependent",
            autonomous=True,
            multi_step=True,
        ),
        active_objective=objective,
    )
    assert replay.disposition == "replay_objective"
    assert replay.effective_request == (
        "Prioritize the provider's own status page."
    )

    audited = advance_active_objective(
        objective,
        request=replay.latest_request,
        profile="research",
        relation=replay.relation,
        disposition=replay.disposition,
        turn_id="turn-4",
        run_id="run-1",
    )
    assert audited.revisions[-1].disposition == "replay_objective"
    assert audited.revisions[-1].request == "Try that exact request again."
    assert audited.latest_user_request() == (
        "Prioritize the provider's own status page."
    )
    assert "Try that exact request again." not in audited.effective_objective_text()


def test_durable_effective_objective_uses_turn_disposition() -> None:
    previous = "Research the incident.\nLater steering: Prioritize primary status sources."

    response_plan = compile_turn_plan(
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
        active_objective=make_active_objective(
            canonical_request="Prioritize primary status sources.",
            base_request="Research the incident.",
            profile="research",
            status="active",
            run_id="run-1",
        ),
    )
    assert response_plan.disposition == "response_only_continuation"
    assert derive_effective_objective(previous, response_plan) == previous

    revise_plan = compile_turn_plan(
        "Actually research only GitHub's official status page.",
        _task(
            intent="narrow incident research",
            operations=[
                SemanticOperation(
                    kind="research",
                    target="public_web",
                    subject_reference="GitHub official status page",
                )
            ],
            relation="revise",
            autonomous=True,
            multi_step=True,
        ),
        active_objective=make_active_objective(
            canonical_request="Prioritize primary status sources.",
            base_request="Research the incident.",
            profile="research",
            status="active",
            run_id="run-1",
        ),
    )
    assert revise_plan.disposition == "revise_objective"
    assert derive_effective_objective(previous, revise_plan) == (
        "Actually research only GitHub's official status page."
    )


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



def test_cross_profile_composite_routes_to_task_graph_boundary() -> None:
    plan = compile_turn_plan(
        "Fix the code and email the result.",
        _task(
            intent="fix code and email result",
            operations=[
                SemanticOperation(kind="modify", target="workspace"),
                SemanticOperation(kind="send", target="email"),
            ],
            autonomous=True,
            multi_step=True,
        ),
        routing_environment={"active_workspace": "omnix"},
    )

    assert plan.lane == "agent"
    assert plan.profile_id is None
    assert plan.run_action == "start_task_graph"
    assert plan.compilation.requires_clarification is False
    assert {
        row.code for row in plan.compilation.anomalies
    } == {"unsupported_composite_profiles"}


def test_active_task_graph_bounded_addition_stays_graph_steering() -> None:
    active = make_active_objective(
        canonical_request="Research the incident and prepare the follow-up.",
        profile="task-graph",
        status="active",
        run_id="graph-run-1",
    )
    plan = compile_turn_plan(
        "Also verify the current provider status.",
        _task(
            intent="verify current provider status",
            operations=[
                SemanticOperation(
                    kind="research",
                    target="public_web",
                    subject_reference="provider status",
                )
            ],
            dependencies=[
                SemanticDataDependency(
                    target="public_web",
                    freshness="current",
                    subject_reference="provider status",
                    retrieval_mode="verify",
                )
            ],
            relation="continue",
            autonomous=True,
        ),
        active_objective=active,
    )

    assert plan.lane == "agent"
    assert plan.profile_id == "research"
    assert plan.run_action == "steer_task_graph"
    assert plan.active_run_id == "graph-run-1"
    assert plan.compilation.evidence_decision.policy.requirement == "required"


def test_ambiguous_active_task_graph_steering_still_clarifies() -> None:
    active = make_active_objective(
        canonical_request="Research the incident and prepare the follow-up.",
        profile="task-graph",
        status="active",
        run_id="graph-run-1",
    )
    task = _task(
        intent="do it",
        operations=[
            SemanticOperation(
                kind="research",
                target="public_web",
                subject_reference="it",
            )
        ],
        relation="continue",
        autonomous=True,
    ).model_copy(
        update={
            "ambiguity": "clarification_required",
            "candidate_interpretations": [
                "research the prior incident",
                "research a different incident",
            ],
        }
    )

    plan = compile_turn_plan(
        "Do it.",
        task,
        active_objective=active,
    )

    assert plan.lane == "chat"
    assert plan.run_action == "clarify"
    assert plan.compilation.requires_clarification is True
