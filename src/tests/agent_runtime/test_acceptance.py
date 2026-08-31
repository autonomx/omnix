from __future__ import annotations

from app.agent_runtime.acceptance import evaluate_acceptance
from app.agent_runtime.contracts import AgentArtifact, AgentEvent, AgentRunSpec, ModelRef, SuccessCriterion


def test_acceptance_requires_model_evidence_to_be_verified_by_omnix() -> None:
    spec = AgentRunSpec(
        run_id="run-1",
        task="Fix tests",
        model=ModelRef(provider_id="test", model_id="model"),
        success_criteria=[SuccessCriterion(id="tests", description="Targeted tests pass")],
        expected_artifacts=["diff"],
    )
    events = [
        AgentEvent(run_id="run-1", event_type="tool.started", payload={"tool_call_id": "1", "tool": "bash", "args": {"command": "python -m pytest -q"}}),
        AgentEvent(run_id="run-1", event_type="tool.completed", payload={"tool_call_id": "1", "tool": "bash", "is_error": False}),
    ]
    result = evaluate_acceptance(
        spec,
        events=events,
        artifacts=[AgentArtifact(run_id="run-1", kind="diff", name="workspace.diff")],
    )
    assert result.passed
    assert result.checks["successful_test_command"]


def test_acceptance_rejects_claimed_completion_without_required_test() -> None:
    spec = AgentRunSpec(
        run_id="run-1",
        task="Fix tests",
        model=ModelRef(provider_id="test", model_id="model"),
        success_criteria=[SuccessCriterion(id="tests", description="Tests pass")],
    )
    result = evaluate_acceptance(spec, events=[], artifacts=[])
    assert not result.passed
    assert "successful_test_command" in result.failures


def test_mutating_coding_run_requires_successful_test_by_default() -> None:
    spec = AgentRunSpec(
        run_id="run-default-coding",
        task="Implement the change",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.write"],
        success_criteria=[
            SuccessCriterion(
                id="generic",
                description="Complete the requested task and report evidence.",
            )
        ],
    )
    result = evaluate_acceptance(spec, events=[], artifacts=[])
    assert not result.passed
    assert "successful_test_command" in result.failures


def test_explicit_required_command_must_succeed() -> None:
    from app.agent_runtime.contracts import AcceptancePlan

    spec = AgentRunSpec(
        run_id="run-required-command",
        task="Fix targeted behavior",
        model=ModelRef(provider_id="test", model_id="model"),
        acceptance_plan=AcceptancePlan(
            required_commands=[["python", "-m", "pytest", "src/tests/target.py", "-q"]],
        ),
    )
    events = [
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.started",
            payload={
                "tool_call_id": "1",
                "tool": "bash",
                "args": {"command": "python -m pytest src/tests/target.py -q"},
            },
        ),
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.completed",
            payload={"tool_call_id": "1", "tool": "bash", "is_error": False},
        ),
    ]
    result = evaluate_acceptance(spec, events=events, artifacts=[])
    assert result.passed
    assert result.checks["required_command:1"]


def test_optional_success_criterion_does_not_create_required_acceptance_check() -> None:
    spec = AgentRunSpec(
        run_id="run-optional",
        task="Inspect",
        profile="research",
        model=ModelRef(provider_id="test", model_id="model"),
        success_criteria=[
            SuccessCriterion(
                id="optional-tests",
                description="Tests pass if applicable",
                required=False,
            )
        ],
    )
    result = evaluate_acceptance(spec, events=[], artifacts=[])
    assert result.passed
    assert "successful_test_command" not in result.checks



def test_ui_task_rejects_unrelated_diff_and_validation() -> None:
    spec = AgentRunSpec(
        run_id="run-ui-unrelated",
        task="Fix Aurora light mode so the Agent run card text is readable",
        objective="Fix Aurora light mode so the Agent run card text is readable",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
        expected_artifacts=["diff"],
    )
    events = [
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.started",
            payload={
                "tool_call_id": "test-1",
                "tool": "powershell",
                "args": {"command": "python -m pytest src/tests/agent_runtime/test_acceptance.py -q"},
            },
        ),
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.completed",
            payload={"tool_call_id": "test-1", "tool": "powershell", "is_error": False},
        ),
    ]
    artifact = AgentArtifact(
        run_id=spec.run_id,
        kind="diff",
        name="workspace.diff",
        metadata={
            "byte_size": 120,
            "modified_paths": ["src/app/live_speech/tts.py"],
            "baseline_conflicts": [],
        },
    )

    result = evaluate_acceptance(spec, events=events, artifacts=[artifact])

    assert not result.passed
    assert "modified_paths_not_task_relevant" in result.failures
    assert "validation_not_task_relevant" in result.failures


def test_ui_task_accepts_web_diff_with_frontend_validation() -> None:
    spec = AgentRunSpec(
        run_id="run-ui-relevant",
        task="Fix Aurora light mode card styling",
        objective="Fix Aurora light mode card styling",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
        expected_artifacts=["diff"],
    )
    events = [
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.started",
            payload={
                "tool_call_id": "test-1",
                "tool": "powershell",
                "args": {
                    "command": "npx vitest run src/apps/web/src/features/chatbot/OmnixRunCard.test.tsx"
                },
            },
        ),
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.completed",
            payload={"tool_call_id": "test-1", "tool": "powershell", "is_error": False},
        ),
    ]
    artifact = AgentArtifact(
        run_id=spec.run_id,
        kind="diff",
        name="workspace.diff",
        metadata={
            "byte_size": 240,
            "modified_paths": [
                "src/apps/web/src/features/chatbot/OmnixRunCard.css",
                "src/apps/web/src/appearance-overrides.css",
            ],
            "baseline_conflicts": [],
        },
    )

    result = evaluate_acceptance(spec, events=events, artifacts=[artifact])

    assert result.passed
    assert result.checks["task_relevant_modified_paths"] is True
    assert result.checks["task_relevant_validation"] is True


def test_ui_task_accepts_frontend_build_as_validation() -> None:
    spec = AgentRunSpec(
        run_id="run-ui-build",
        task="Change the chat UI profile label",
        objective="Change the chat UI profile label",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
        expected_artifacts=["diff"],
    )
    events = [
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.started",
            payload={
                "tool_call_id": "build-1",
                "tool": "powershell",
                "args": {"command": "npm run build"},
            },
        ),
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.completed",
            payload={"tool_call_id": "build-1", "tool": "powershell", "is_error": False},
        ),
    ]
    artifact = AgentArtifact(
        run_id=spec.run_id,
        kind="diff",
        name="workspace.diff",
        metadata={
            "byte_size": 120,
            "modified_paths": ["src/apps/web/src/features/chatbot/ChatIdentityModeControl.tsx"],
            "baseline_conflicts": [],
        },
    )

    result = evaluate_acceptance(spec, events=events, artifacts=[artifact])

    assert result.passed
    assert result.checks["successful_test_command"] is True
    assert result.checks["task_relevant_validation"] is True


def test_runtime_diff_must_be_nonempty() -> None:
    spec = AgentRunSpec(
        run_id="run-empty-diff",
        task="Implement the change",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
        expected_artifacts=["diff"],
    )
    events = [
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.started",
            payload={
                "tool_call_id": "test-1",
                "tool": "bash",
                "args": {"command": "python -m pytest -q"},
            },
        ),
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.completed",
            payload={"tool_call_id": "test-1", "tool": "bash", "is_error": False},
        ),
    ]
    artifact = AgentArtifact(
        run_id=spec.run_id,
        kind="diff",
        name="workspace.diff",
        metadata={"byte_size": 0, "modified_paths": [], "baseline_conflicts": []},
    )

    result = evaluate_acceptance(spec, events=events, artifacts=[artifact])

    assert not result.passed
    assert "empty_diff_artifact" in result.failures


def test_ui_task_can_verify_an_already_satisfied_change_without_new_diff() -> None:
    spec = AgentRunSpec(
        run_id="run-ui-noop",
        task="Increase the spacing between the fullscreen and Personality buttons",
        objective="Increase the spacing between the fullscreen and Personality buttons",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
        expected_artifacts=["diff"],
    )
    events = [
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.started",
            payload={
                "tool_call_id": "test-1",
                "tool": "powershell",
                "args": {
                    "command": "npx vitest run src/apps/web/src/features/chatbot/ChatbotWorkspace.test.tsx"
                },
            },
        ),
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.completed",
            payload={"tool_call_id": "test-1", "tool": "powershell", "is_error": False},
        ),
    ]
    artifact = AgentArtifact(
        run_id=spec.run_id,
        kind="diff",
        name="workspace.diff",
        metadata={"byte_size": 0, "modified_paths": [], "baseline_conflicts": []},
    )

    result = evaluate_acceptance(spec, events=events, artifacts=[artifact])

    assert result.passed
    assert result.checks["already_satisfied_without_diff"] is True
    assert "empty_diff_artifact" not in result.failures


def test_preexisting_dirty_file_changed_by_agent_fails_acceptance() -> None:
    spec = AgentRunSpec(
        run_id="run-baseline-conflict",
        task="Implement the backend change",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
        expected_artifacts=["diff"],
    )
    events = [
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.started",
            payload={
                "tool_call_id": "test-1",
                "tool": "bash",
                "args": {"command": "python -m pytest -q"},
            },
        ),
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.completed",
            payload={"tool_call_id": "test-1", "tool": "bash", "is_error": False},
        ),
    ]
    artifact = AgentArtifact(
        run_id=spec.run_id,
        kind="diff",
        name="workspace.diff",
        metadata={
            "byte_size": 100,
            "modified_paths": ["src/app/agent_runtime/service.py"],
            "baseline_conflicts": ["src/app/live_speech/tts.py"],
        },
    )

    result = evaluate_acceptance(spec, events=events, artifacts=[artifact])

    assert not result.passed
    assert "preexisting_dirty_paths_modified" in result.failures
