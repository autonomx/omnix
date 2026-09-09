from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"patch anchor missing in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1. Size default coding-quality runs for implement -> review -> repair -> re-review.
service_path = "src/app/agent_runtime/service.py"
replace_once(
    service_path,
    "    ReviewSnapshot,\n    SelfReviewResult,\n",
    "    ReviewSnapshot,\n    RunLimits,\n    SelfReviewResult,\n",
)
replace_once(
    service_path,
    "_BLOCKED_SETTLE = {\n    \"waiting_for_approval\",\n    \"waiting_for_input\",\n    \"waiting_for_children\",\n    \"pause_requested\",\n    \"paused\",\n    \"cancel_requested\",\n    \"cancelled\",\n}\n\n\ndef _is_structured_self_review_message",
    "_BLOCKED_SETTLE = {\n    \"waiting_for_approval\",\n    \"waiting_for_input\",\n    \"waiting_for_children\",\n    \"pause_requested\",\n    \"paused\",\n    \"cancel_requested\",\n    \"cancelled\",\n}\n\n_QUALITY_DEFAULT_MAX_STEPS = {\n    \"standard\": 350,\n    \"strict\": 500,\n    \"critical\": 750,\n}\n\n\ndef _quality_sized_run_spec(spec: AgentRunSpec) -> AgentRunSpec:\n    \"\"\"Give default coding runs enough global authority to converge through review.\n\n    The parent budget is a global circuit breaker: implementer work and actual\n    child-review spend are both charged to it. The generic 200-step default is\n    too small for a normal strict cycle once a reviewer finds a real issue and\n    the repaired immutable snapshot must be reviewed again. Only implicit\n    defaults are raised; any caller-supplied RunLimits remain authoritative.\n    \"\"\"\n\n    if (\n        spec.profile != \"coding\"\n        or \"diff\" not in spec.expected_artifacts\n        or spec.quality_policy == \"off\"\n        or \"limits\" in spec.model_fields_set\n    ):\n        return spec\n    max_steps = _QUALITY_DEFAULT_MAX_STEPS.get(spec.quality_policy, 500)\n    max_tool_calls = max(spec.limits.max_tool_calls, int(max_steps * 2.5))\n    limits = spec.limits.model_copy(\n        update={\n            \"max_steps\": max_steps,\n            \"max_tool_calls\": max_tool_calls,\n        }\n    )\n    return spec.model_copy(update={\"limits\": limits})\n\n\ndef _is_structured_self_review_message",
)
replace_once(
    service_path,
    "        resolved = resolve_run_model_fidelity(spec)\n        return super().start_with_context(\n            resolved,",
    "        resolved = _quality_sized_run_spec(resolve_run_model_fidelity(spec))\n        return super().start_with_context(\n            resolved,",
)

# 2. Persist the exact budget failure before the run becomes terminal.
budget_path = "src/app/agent_runtime/budget.py"
replace_once(
    budget_path,
    "from .contracts import AgentRunSnapshot\n",
    "from .contracts import AgentEvent, AgentRunSnapshot\n",
)
replace_once(
    budget_path,
    "        repository.update_state(\n            snapshot.run_id,\n            expected_revision=current.revision,\n            status=\"failed\",\n            desired_state=\"cancelled\",\n            last_error=reason[:2000],\n        )\n",
    "        repository.append_event(\n            AgentEvent(\n                run_id=snapshot.run_id,\n                event_type=\"run.failed\",\n                payload={\n                    \"source\": \"omnix_budget\",\n                    \"error\": reason[:2000],\n                    \"provider_error_code\": \"agent_run_budget_exhausted\",\n                    \"retryable\": False,\n                    \"error_scope\": \"run\",\n                },\n            )\n        )\n        repository.update_state(\n            snapshot.run_id,\n            expected_revision=current.revision,\n            status=\"failed\",\n            desired_state=\"cancelled\",\n            last_error=reason[:2000],\n        )\n",
)

# 3. Pi's OpenAI transport drops the JSON body for non-2xx 409 responses. The
# Omnix model gateway only uses 409 for run-local budget authority, so preserve
# that identity even when Pi reports merely "409 status code (no body)".
pi_runtime_path = "src/app/agent_runtime/pi_runtime.py"
replace_once(
    pi_runtime_path,
    "    elif \"usagelimitexceeded\" in lowered or \"usage limit\" in lowered:\n        provider_error_code = \"model_usage_limit_exceeded\"\n",
    "    elif (\n        \"409 status code\" in lowered\n        and str(message.get(\"provider\") or \"\").strip().casefold() == \"omnix\"\n    ):\n        provider_error_code = \"agent_run_budget_exhausted\"\n        retryable = False\n        error_scope = \"run\"\n    elif \"usagelimitexceeded\" in lowered or \"usage limit\" in lowered:\n        provider_error_code = \"model_usage_limit_exceeded\"\n",
)

# 4. A path-scoped or summary-only git diff is useful inspection, but cannot
# satisfy the authoritative complete-final-diff validation obligation.
quality_path = "src/app/agent_runtime/coding_quality.py"
replace_once(
    quality_path,
    "_DIFF_REVIEW = re.compile(r\"\\bgit\\s+(?:-c\\s+\\S+\\s+)?diff\\b\", re.I)\n",
    "_DIFF_REVIEW = re.compile(r\"\\bgit\\s+(?:-c\\s+\\S+\\s+)?diff\\b\", re.I)\n_DIFF_SUMMARY_ONLY = re.compile(\n    r\"(?:^|\\s)--(?:stat|shortstat|numstat|name-only|name-status|summary|dirstat(?:=[^\\s]+)?|quiet|check)(?:\\s|$)\",\n    re.I,\n)\n_DIFF_EXPLICIT_FILE = re.compile(\n    r\"(?:^|\\s)[\\\"']?(?:src|tests?|packages?|apps?|docs?)[/\\\\][^\\s\\\"']+|\"\n    r\"(?:^|\\s)[\\\"']?[^\\s\\\"']+\\.(?:py|pyi|js|jsx|ts|tsx|css|scss|html|go|rs|java|rb|php|cs|cpp|c|h)[\\\"']?(?:\\s|$)\",\n    re.I,\n)\n",
)
replace_once(
    quality_path,
    "def validation_kind_for_command(command: str) -> str | None:\n    value = str(command or \"\")\n    if _DIFF_REVIEW.search(value):\n        return \"diff_review\"\n",
    "def diff_review_command_is_complete(command: str) -> bool:\n    \"\"\"Return true only when git diff inspects the repository-wide final diff.\"\"\"\n\n    value = str(command or \"\").strip()\n    match = _DIFF_REVIEW.search(value)\n    if match is None:\n        return False\n    tail = value[match.end() :]\n    if _DIFF_SUMMARY_ONLY.search(tail):\n        return False\n    # `--` followed by a non-option is an explicit pathspec. A bare option such\n    # as --no-ext-diff is allowed and is the canonical validation command.\n    if re.search(r\"(?:^|\\s)--\\s+(?!--)\\S\", tail):\n        return False\n    if _DIFF_EXPLICIT_FILE.search(tail):\n        return False\n    return True\n\n\ndef validation_kind_for_command(command: str) -> str | None:\n    value = str(command or \"\")\n    if _DIFF_REVIEW.search(value):\n        return \"diff_review\"\n",
)
replace_once(
    quality_path,
    "    success = not bool(event.payload.get(\"is_error\")) and not bool(event.payload.get(\"error\"))\n",
    "    complete_diff_review = kind != \"diff_review\" or diff_review_command_is_complete(command)\n    success = (\n        not bool(event.payload.get(\"is_error\"))\n        and not bool(event.payload.get(\"error\"))\n        and complete_diff_review\n    )\n",
)
replace_once(
    quality_path,
    "    metadata: dict[str, object] = {\n        \"tool_call_id\": call_id,\n        \"capability_id\": capability_id or None,\n    }\n    if kind == \"browser\":\n",
    "    metadata: dict[str, object] = {\n        \"tool_call_id\": call_id,\n        \"capability_id\": capability_id or None,\n    }\n    if kind == \"diff_review\" and not complete_diff_review:\n        metadata[\"failure_class\"] = \"incomplete_diff_scope\"\n    if kind == \"browser\":\n",
)

# 5. Regression coverage.
Path("src/tests/agent_runtime/test_quality_budget_convergence.py").write_text(
    '''from __future__ import annotations\n\nfrom app.agent_runtime.contracts import AgentRunSpec, ModelRef, RunLimits\nfrom app.agent_runtime.service import _quality_sized_run_spec\n\n\ndef _spec(*, policy: str = "strict", limits: RunLimits | None = None, profile: str = "coding") -> AgentRunSpec:\n    kwargs = {} if limits is None else {"limits": limits}\n    return AgentRunSpec(\n        task="Fix a coding bug",\n        profile=profile,\n        model=ModelRef(provider_id="chatgpt_codex", model_id="gpt-5.6-luna"),\n        expected_artifacts=["diff"] if profile == "coding" else [],\n        quality_policy=policy,\n        **kwargs,\n    )\n\n\ndef test_implicit_strict_coding_budget_supports_review_repair_rereview_cycle() -> None:\n    sized = _quality_sized_run_spec(_spec())\n    assert sized.limits.max_steps == 500\n    assert sized.limits.max_tool_calls == 1250\n\n\ndef test_quality_budget_scales_by_policy() -> None:\n    assert _quality_sized_run_spec(_spec(policy="standard")).limits.max_steps == 350\n    assert _quality_sized_run_spec(_spec(policy="critical")).limits.max_steps == 750\n\n\ndef test_explicit_limits_remain_authoritative_even_when_equal_to_generic_defaults() -> None:\n    explicit = RunLimits()\n    sized = _quality_sized_run_spec(_spec(limits=explicit))\n    assert sized.limits == explicit\n    assert sized.limits.max_steps == 200\n\n\ndef test_non_coding_and_quality_off_runs_keep_generic_defaults() -> None:\n    noncoding = _quality_sized_run_spec(_spec(profile="research"))\n    assert noncoding.limits.max_steps == 200\n    off = _quality_sized_run_spec(_spec(policy="off"))\n    assert off.limits.max_steps == 200\n''',
    encoding="utf-8",
)

Path("src/tests/agent_runtime/test_final_diff_validation_scope.py").write_text(
    '''from __future__ import annotations\n\nfrom app.agent_runtime.coding_quality import (\n    diff_review_command_is_complete,\n    validation_result_from_tool_event,\n)\nfrom app.agent_runtime.contracts import AgentEvent, TaskRevision, ValidationSpec\n\n\ndef _revision() -> TaskRevision:\n    return TaskRevision(\n        revision_id="revision-1",\n        run_id="run-1",\n        sequence=1,\n        user_instruction="Fix the UI",\n        effective_objective="Fix the UI",\n        validation_plan=[\n            ValidationSpec(\n                id="final-diff-review",\n                kind="diff_review",\n                description="Inspect complete final diff",\n                required=True,\n            )\n        ],\n    )\n\n\ndef _result(command: str):\n    return validation_result_from_tool_event(\n        AgentEvent(\n            run_id="run-1",\n            event_type="tool.completed",\n            payload={\n                "tool_call_id": "call-1",\n                "args": {"command": command},\n                "result": {"details": {"exitCode": 0, "output": "diff"}},\n                "is_error": False,\n            },\n        ),\n        run_id="run-1",\n        task_revision_id="revision-1",\n        workspace_state_id="state-1",\n        revision=_revision(),\n    )\n\n\ndef test_complete_diff_commands_are_authoritative_validation() -> None:\n    assert diff_review_command_is_complete("git diff --no-ext-diff")\n    assert diff_review_command_is_complete("git diff HEAD")\n    result = _result("git diff --no-ext-diff")\n    assert result is not None and result.success\n\n\ndef test_path_scoped_diff_cannot_satisfy_final_diff_review() -> None:\n    assert not diff_review_command_is_complete("git diff -- src/apps/web/src/styles.css")\n    assert not diff_review_command_is_complete("git diff src/app/agent_runtime/repository.py")\n    result = _result("git diff -- src/apps/web/src/styles.css")\n    assert result is not None\n    assert not result.success\n    assert result.metadata["failure_class"] == "incomplete_diff_scope"\n\n\ndef test_summary_only_diff_cannot_satisfy_final_diff_review() -> None:\n    assert not diff_review_command_is_complete("git diff --name-only")\n    assert not diff_review_command_is_complete("git diff --stat")\n''',
    encoding="utf-8",
)

# Add one transport regression to the existing provider-failure suite.
provider_test = Path("src/tests/agent_runtime/test_pi_provider_failure_recovery.py")
provider_text = provider_test.read_text(encoding="utf-8")
provider_case = '''\n\ndef test_bare_omnix_gateway_409_is_preserved_as_run_budget_exhaustion() -> None:\n    event = normalize_pi_event(\n        "run-local-budget-bare-409",\n        {\n            "type": "message_end",\n            "message": {\n                "role": "assistant",\n                "provider": "omnix",\n                "stopReason": "error",\n                "errorMessage": "409 status code (no body)",\n                "content": [],\n            },\n        },\n        task_revision_id="revision-budget-409",\n    )\n    assert event is not None\n    assert event.event_type == "run.failed"\n    assert event.payload["provider_error_code"] == "agent_run_budget_exhausted"\n    assert event.payload["retryable"] is False\n    assert event.payload["error_scope"] == "run"\n'''
if "test_bare_omnix_gateway_409_is_preserved_as_run_budget_exhaustion" not in provider_text:
    provider_test.write_text(provider_text.rstrip() + provider_case + "\n", encoding="utf-8")

# Extend the existing PostgreSQL budget test to require a durable causal event.
persistence_test = Path("src/tests/persistence/test_agent_budget_integration.py")
persistence_text = persistence_test.read_text(encoding="utf-8")
old = '''        with pytest.raises(AgentBudgetError, match="budget_max_steps_exceeded"):\n            manager.authorize_model_call(step_run, provider_id="lmstudio")\n\n        tool_run = _run(\n'''
new = '''        with pytest.raises(AgentBudgetError, match="budget_max_steps_exceeded"):\n            manager.authorize_model_call(step_run, provider_id="lmstudio")\n        with unit_of_work(database) as work:\n            repository = PostgresAgentRunRepository(work.connection, context)\n            step_snapshot = repository.get_run(step_run)\n            step_events = repository.list_events(step_run, after_sequence=0, limit=100)\n            work.rollback()\n        assert step_snapshot is not None\n        assert step_snapshot.status == "failed"\n        assert step_snapshot.last_error == "budget_max_steps_exceeded"\n        budget_failure = next(event for event in step_events if event.event_type == "run.failed")\n        assert budget_failure.payload["source"] == "omnix_budget"\n        assert budget_failure.payload["error"] == "budget_max_steps_exceeded"\n        assert budget_failure.payload["provider_error_code"] == "agent_run_budget_exhausted"\n\n        tool_run = _run(\n'''
if "budget_failure.payload[\"source\"]" not in persistence_text:
    if old not in persistence_text:
        raise RuntimeError("budget integration test anchor missing")
    persistence_test.write_text(persistence_text.replace(old, new, 1), encoding="utf-8")

print("quality budget convergence patch applied")
