from __future__ import annotations

from types import SimpleNamespace

from app.agent_runtime import chat_bridge
from app.agent_runtime.active_objective import (
    build_routing_environment,
    normalize_objective_relation,
    objective_continuity_candidate,
    objective_resume_replays_prior_request,
    resolve_active_objective,
)
from app.agent_runtime.chat_bridge import route_typed_chat_turn
from app.agent_runtime.semantic_task import (
    SemanticOperation,
    SemanticSubject,
    SemanticTask,
    compile_semantic_task,
)


def _blocked_coding_metadata(task: str) -> dict:
    return {
        "agent_start": {
            "status": "failed",
            "durable": False,
            "reason": "workspace_required",
        },
        "agent_run": {
            "run_id": None,
            "status": "failed",
            "profile": "coding",
            "task": task,
            "revision": None,
            "last_error": "workspace_required",
        },
    }


def test_active_objective_recovers_blocked_task_across_intervening_chat() -> None:
    task = "change the text Personality to Profile. make the change."
    objective = chat_bridge.make_active_objective(
        canonical_request=task,
        profile="coding",
        status="blocked",
        blocking_reason="workspace_required",
        originating_turn_id="task-turn",
        last_relevant_turn_id="failed-turn",
    ).model_dump(mode="json")
    session = SimpleNamespace(
        messages=[
            SimpleNamespace(id="task-turn", role="user", content=task, metadata={}),
            SimpleNamespace(
                id="failed-turn",
                role="assistant",
                content="No coding workspace is configured.",
                metadata=_blocked_coding_metadata(task),
            ),
            SimpleNamespace(
                id="side-user",
                role="user",
                content="what happened?",
                metadata={"active_objective": objective},
            ),
            SimpleNamespace(
                id="side-assistant",
                role="assistant",
                content="The workspace was missing.",
                metadata={"active_objective": objective},
            ),
        ]
    )
    current = SimpleNamespace(
        id="retry-turn",
        role="user",
        content="i didnt include the project folder before. try again in code",
        metadata={},
    )

    resolved = resolve_active_objective(session, current)

    assert resolved is not None
    assert resolved.canonical_request == task
    assert resolved.profile == "coding"
    assert resolved.status == "blocked"
    assert resolved.blocking_reason == "workspace_required"




def test_long_objective_is_preserved_but_routing_projection_is_bounded() -> None:
    request = "start " + ("x" * 12000) + " end"
    objective = chat_bridge.make_active_objective(
        canonical_request=request,
        profile="coding",
        status="blocked",
    )

    projection = objective.reference_text(max_request_chars=8000)

    assert objective.canonical_request == request
    assert len(projection) < len(request)
    assert "objective text omitted from routing projection" in projection
    assert "effective_objective_digest" in projection

def test_structured_objective_routing_projection_is_bounded() -> None:
    objective = chat_bridge.make_active_objective(
        canonical_request="base " + ("x" * 5000),
        profile="coding",
        status="active",
        run_id="run-bounded",
    )
    for index in range(20):
        objective = chat_bridge.advance_active_objective(
            objective,
            request=f"revision-{index} " + ("y" * 2500),
            profile="coding",
            relation="continue",
            disposition="continue_objective",
            turn_id=f"turn-{index}",
            run_id="run-bounded",
        )

    projection = objective.reference_text(max_request_chars=4000)

    assert len(projection) < 20000
    assert '"revision_count":20' in projection
    assert '"older_revisions_omitted":12' in projection
    assert "effective_objective_digest" in projection
    assert "revision-19" in projection


def test_nonterminal_agent_run_preserves_explicit_steered_objective() -> None:
    original = "Check CI and diagnose the failure."
    revised = "Fix the stale assertion and the narrow production bug."
    objective = chat_bridge.make_active_objective(
        canonical_request=revised,
        profile="coding",
        status="active",
        run_id="run-steered",
        originating_turn_id="fix-turn",
    ).model_dump(mode="json")
    session = SimpleNamespace(
        messages=[
            SimpleNamespace(
                id="steered-run",
                role="assistant",
                content="Steering sent.",
                metadata={
                    "active_objective": objective,
                    "agent_run": {
                        "run_id": "run-steered",
                        "status": "running",
                        "profile": "coding",
                        "task": original,
                        "revision": 4,
                        "last_error": None,
                    },
                },
            )
        ]
    )
    current = SimpleNamespace(
        id="retry-turn",
        role="user",
        content="try that exact request again",
        metadata={},
    )

    resolved = resolve_active_objective(session, current)

    assert resolved is not None
    assert resolved.canonical_request == revised
    assert resolved.run_id == "run-steered"
    assert resolved.status == "active"


def test_resume_replay_requires_an_opaque_prior_request_reference() -> None:
    assert objective_resume_replays_prior_request("try again")
    assert objective_resume_replays_prior_request(
        "Try that exact implementation request again."
    )
    assert objective_resume_replays_prior_request("run it again")
    assert objective_resume_replays_prior_request(
        "i didnt include the project folder before. try again in code"
    )
    assert not objective_resume_replays_prior_request(
        "Run the focused test again."
    )
    assert not objective_resume_replays_prior_request(
        "Run the semantic-task tests again."
    )


def test_continuity_override_keeps_complete_retry_command_authoritative() -> None:
    objective = chat_bridge.make_active_objective(
        canonical_request="Fix the stale assertion and the narrow production bug.",
        profile="coding",
        status="active",
        run_id="run-steered",
    )
    task = SemanticTask(
        intent="rerun the focused test",
        operations=[
            SemanticOperation(
                kind="execute",
                target="repository",
                subject_reference="focused test",
            )
        ],
        objective_relation="resume",
        autonomous=True,
        reason_code="rerun_focused_test",
    )
    compilation = compile_semantic_task("Run the focused test again.", task)

    assert chat_bridge._continuity_content_override(
        "Run the focused test again.",
        objective,
        task,
        compilation,
    ) == "Run the focused test again."
    replay_task = SemanticTask(
        intent="retry the exact prior implementation request",
        operations=[
            SemanticOperation(
                kind="modify",
                target="repository",
                subject_reference="prior implementation request",
            )
        ],
        objective_relation="resume",
        request_completeness="context_dependent",
        replay_target="latest_authoritative",
        autonomous=True,
        reason_code="retry_prior_implementation",
    )
    replay_compilation = compile_semantic_task(
        "Try that exact implementation request again.",
        replay_task,
    )
    assert chat_bridge._continuity_content_override(
        "Try that exact implementation request again.",
        objective,
        replay_task,
        replay_compilation,
    ) == "Fix the stale assertion and the narrow production bug."


def test_terminal_agent_run_closes_carried_active_objective() -> None:
    task = "change the text Personality to Profile. make the change."
    stale = chat_bridge.make_active_objective(
        canonical_request=task,
        profile="coding",
        status="active",
        run_id="run-finished",
    ).model_dump(mode="json")
    session = SimpleNamespace(
        messages=[
            SimpleNamespace(
                id="completed-run",
                role="assistant",
                content="Agent run completed.",
                metadata={
                    "active_objective": stale,
                    "agent_run": {
                        "run_id": "run-finished",
                        "status": "completed",
                        "profile": "coding",
                        "task": task,
                        "revision": 4,
                        "last_error": None,
                    },
                },
            )
        ]
    )
    current = SimpleNamespace(
        id="later-turn",
        role="user",
        content="try again",
        metadata={},
    )

    assert resolve_active_objective(session, current) is None

def test_routing_environment_exposes_attached_workspace_without_full_path(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    selected = tmp_path / "omnix"
    selected.mkdir()
    message = SimpleNamespace(
        metadata={
            "workspace_root": str(selected),
            "image_data_url": "data:image/png;base64,YWJj",
        }
    )

    environment = build_routing_environment(message)

    assert environment.active_workspace == "omnix"
    assert environment.workspace_source == "turn_attachment"
    assert environment.workspace_attached_this_turn is True
    assert set(environment.attachment_kinds) == {"local_folder", "image"}
    assert str(tmp_path) not in environment.model_dump_json()


def test_continuity_marker_only_requests_semantic_resolution() -> None:
    assert objective_continuity_candidate(
        "i didnt include the project folder before. try again in code"
    )
    assert objective_continuity_candidate("fix it")
    assert not objective_continuity_candidate(
        "Explain TCP congestion control from first principles"
    )


def test_contextual_retry_resumes_prior_coding_objective_with_current_workspace(
    monkeypatch,
    tmp_path,
) -> None:
    selected = tmp_path / "omnix"
    selected.mkdir()
    original_task = "change the text Personality to Profile. make the change."
    objective = chat_bridge.make_active_objective(
        canonical_request=original_task,
        profile="coding",
        status="blocked",
        blocking_reason="workspace_required",
        originating_turn_id="original-task",
        last_relevant_turn_id="failed-agent",
    ).model_dump(mode="json")
    seen: list[dict] = []
    started = []

    class _Parser:
        def parse_contextual(
            self,
            latest_user_message: str,
            *,
            reference_context: str = "",
            previous_objective: str = "",
            current_environment=None,
        ):
            seen.append(
                {
                    "latest": latest_user_message,
                    "reference_context": reference_context,
                    "previous_objective": previous_objective,
                    "current_environment": current_environment,
                }
            )
            return SemanticTask(
                intent="resume the blocked workspace edit",
                subjects=[
                    SemanticSubject(
                        target="workspace",
                        reference="the previous Personality to Profile edit",
                    )
                ],
                operations=[
                    SemanticOperation(kind="inspect", target="workspace"),
                    SemanticOperation(kind="modify", target="workspace"),
                    SemanticOperation(kind="validate", target="workspace"),
                ],
                autonomous=True,
                multi_step=True,
                objective_relation="resume",
                request_completeness="context_dependent",
                ambiguity="resolvable_from_context",
                confidence=0.99,
                reason_code="resume_blocked_workspace_edit",
            )

    class _Service:
        def get(self, _run_id):
            return None

        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                superseded_by_run_id=None,
                spec=spec,
            )

    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_ROUTING_MODE", "v2")
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())

    session = SimpleNamespace(
        id="chat-objective-resume",
        provider_id="test",
        model_id="model",
        messages=[
            SimpleNamespace(
                id="original-task",
                role="user",
                content=original_task,
                metadata={},
            ),
            SimpleNamespace(
                id="failed-agent",
                role="assistant",
                content="Agent request could not start because no coding workspace is configured.",
                metadata={
                    **_blocked_coding_metadata(original_task),
                    "active_objective": objective,
                },
            ),
            SimpleNamespace(
                id="intervening-user",
                role="user",
                content="okay",
                metadata={"active_objective": objective},
            ),
            SimpleNamespace(
                id="intervening-assistant",
                role="assistant",
                content="Attach the folder when ready.",
                metadata={"active_objective": objective},
            ),
        ],
    )
    message = SimpleNamespace(
        id="retry-turn",
        role="user",
        content="i didnt include the project folder before. try again in code",
        metadata={"workspace_root": str(selected)},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=_Parser(),
        routing_context_factory=lambda: SimpleNamespace(
            reference_context="User: the requested label change is Personality to Profile."
        ),
    )

    assert result is not None
    assert len(seen) == 1
    assert original_task in seen[0]["previous_objective"]
    assert seen[0]["current_environment"]["active_workspace"] == "omnix"
    assert seen[0]["current_environment"]["workspace_attached_this_turn"] is True
    assert len(started) == 1
    assert started[0].task == original_task
    assert started[0].objective == original_task
    assert started[0].profile == "coding"
    assert started[0].workspace.root == str(selected.resolve())
    assert result.metadata["routing_decision"]["production_router"] == "semantic_v2"
    assert result.metadata["semantic_task"]["objective_relation"] == "resume"
    assert result.metadata["active_objective"]["canonical_request"] == original_task


def test_revised_coding_request_replaces_objective_and_reverses_ui_rename(
    monkeypatch,
    tmp_path,
) -> None:
    selected = tmp_path / "omnix"
    selected.mkdir()
    original_task = "change the title personality to profile in omnix chat"
    revised_task = "now, change the title profile to personality in omnix chat"
    objective = chat_bridge.make_active_objective(
        canonical_request=original_task,
        profile="coding",
        status="active",
        originating_turn_id="original-task",
        last_relevant_turn_id="original-agent",
        run_id="original-run",
    ).model_dump(mode="json")
    started = []
    reference_contexts = []

    class _Parser:
        def parse_contextual(self, _latest_user_message: str, **_kwargs):
            return SemanticTask(
                intent="reverse the prior Omnix chat label rename",
                subjects=[
                    SemanticSubject(
                        target="workspace",
                        reference="Profile label in Omnix chat",
                    )
                ],
                operations=[
                    SemanticOperation(kind="inspect", target="workspace"),
                    SemanticOperation(kind="modify", target="workspace"),
                    SemanticOperation(kind="validate", target="workspace"),
                ],
                autonomous=True,
                multi_step=True,
                objective_relation="revise",
                ambiguity="resolvable_from_context",
                confidence=0.99,
                reason_code="reverse_workspace_label_rename",
            )

    class _Service:
        def get(self, _run_id):
            return None

        def start_with_context(self, spec, *, reference_context="", **_kwargs):
            started.append(spec)
            reference_contexts.append(reference_context)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                superseded_by_run_id=None,
                spec=spec,
            )

    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    session = SimpleNamespace(
        id="chat-objective-revision",
        provider_id="test",
        model_id="model",
        messages=[
            SimpleNamespace(
                id="original-agent",
                role="assistant",
                content="Started coding Agent run original-run.",
                metadata={"active_objective": objective},
            )
        ],
    )
    message = SimpleNamespace(
        id="revision-turn",
        role="user",
        content=revised_task,
        metadata={"workspace_root": str(selected)},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=_Parser(),
        routing_context_factory=lambda: SimpleNamespace(
            reference_context="The earlier request renamed Personality to Profile."
        ),
    )

    assert result is not None
    assert len(started) == 1
    assert started[0].task == revised_task
    assert started[0].objective == revised_task
    assert "Latest user revision" not in started[0].task
    assert original_task not in started[0].task
    assert result.metadata["active_objective"]["canonical_request"] == revised_task
    assert "The earlier request renamed Personality to Profile." not in reference_contexts[0]
    assert all(
        criterion.id != "workspace-ui-target"
        for criterion in started[0].success_criteria
    )


def test_resume_recovers_latest_request_from_legacy_stacked_objective() -> None:
    original_task = "change the title personality to profile in omnix chat"
    revised_task = "now, change the title profile to personality in omnix chat"
    legacy = f"{original_task}\n\nLatest user revision:\n{revised_task}"

    assert chat_bridge._latest_canonical_request(legacy) == revised_task


def test_semantic_resume_cannot_discard_a_complete_latest_command() -> None:
    previous_task = "now, change the title profile to personality in omnix chat"
    latest_task = "now, change the title personality to profile in omnix chat"
    objective = chat_bridge.make_active_objective(
        canonical_request=previous_task,
        profile="coding",
        status="active",
        run_id="previous-run",
    )
    semantic_task = SemanticTask(
        intent="change the Omnix chat label",
        subjects=[SemanticSubject(target="workspace", reference="Omnix chat label")],
        operations=[SemanticOperation(kind="modify", target="workspace")],
        autonomous=True,
        objective_relation="resume",
        ambiguity="none",
        confidence=0.99,
        reason_code="same_workspace_task",
    )
    compilation = compile_semantic_task(latest_task, semantic_task)

    assert not objective_continuity_candidate(latest_task)
    assert (
        chat_bridge._continuity_content_override(
            latest_task,
            objective,
            semantic_task,
            compilation,
        )
        == latest_task
    )


def test_contextual_turn_fails_closed_after_bounded_semantic_retry(
    monkeypatch,
    tmp_path,
) -> None:
    task = "change the text Personality to Profile. make the change."
    objective = chat_bridge.make_active_objective(
        canonical_request=task,
        profile="coding",
        status="blocked",
        blocking_reason="workspace_required",
    ).model_dump(mode="json")
    calls: list[dict] = []

    class _FailingParser:
        def parse_contextual(
            self,
            latest_user_message: str,
            *,
            reference_context: str = "",
            previous_objective: str = "",
            current_environment=None,
        ):
            calls.append(
                {
                    "latest": latest_user_message,
                    "reference_context": reference_context,
                    "previous_objective": previous_objective,
                    "current_environment": current_environment,
                }
            )
            raise RuntimeError("semantic parser unavailable")

    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_ROUTING_MODE", "v2")
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    session = SimpleNamespace(
        id="chat-parser-failure-context",
        provider_id="test",
        model_id="model",
        messages=[
            SimpleNamespace(
                id="blocked",
                role="assistant",
                content="Agent request could not start.",
                metadata={
                    **_blocked_coding_metadata(task),
                    "active_objective": objective,
                },
            )
        ],
    )
    message = SimpleNamespace(
        id="retry",
        role="user",
        content="try again in code",
        metadata={},
    )
    very_long_context = "older context " * 1200 + "\nUser: Personality to Profile."

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=_FailingParser(),
        routing_context_factory=lambda: SimpleNamespace(
            reference_context=very_long_context
        ),
    )

    assert result is not None
    assert len(calls) == 2
    assert len(calls[1]["reference_context"]) <= 6040
    assert calls[1]["previous_objective"]
    assert result.metadata["semantic_gate"]["accepted"] is False
    assert result.metadata["semantic_gate"]["reason"] == "semantic_parser_unavailable"
    assert result.metadata["routing_decision"]["production_router"] == "semantic_v2"
    assert result.metadata["routing_decision"]["production_lane"] == "chat"
    assert "won't guess" in result.content


def test_objective_relation_normalization_distinguishes_retry_noun_from_retry_command() -> None:
    assert (
        normalize_objective_relation(
            "also check the retry path",
            "continue",
        )
        == "continue"
    )
    assert (
        normalize_objective_relation(
            "Also keep it when switching modes.",
            "revise",
        )
        == "continue"
    )
    assert (
        normalize_objective_relation(
            "Try that exact implementation request again.",
            "revise",
        )
        == "resume"
    )
    assert (
        normalize_objective_relation(
            "Actually compare it with AMD instead.",
            "continue",
        )
        == "revise"
    )


def test_response_only_follow_up_can_remain_on_active_agent_boundary() -> None:
    objective = chat_bridge.make_active_objective(
        canonical_request="Research the current incident and summarize the impact.",
        profile="research",
        status="active",
        run_id="active-research-run",
    )
    task = SemanticTask(
        intent="summarize the confirmed findings",
        subjects=[],
        operations=[SemanticOperation(kind="explain", target="conversation")],
        autonomous=False,
        multi_step=False,
        objective_relation="continue",
        ambiguity="resolvable_from_context",
        confidence=0.99,
        reason_code="summarize_active_research",
    )
    compilation = compile_semantic_task(
        "Give me a short conclusion and separate confirmed facts from uncertainty.",
        task,
    )

    assert compilation.lane == "chat"
    assert compilation.action_intents == []

    promoted = chat_bridge._promote_active_agent_response_continuation(
        objective,
        task,
        compilation,
        latest_user_message=(
            "Give me a short conclusion and separate confirmed facts from uncertainty."
        ),
    )

    assert promoted is not None
    assert promoted.lane == "agent"
    assert promoted.profile_id == "research"
    assert promoted.action_intents == []
