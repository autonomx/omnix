from __future__ import annotations

from app.agent_runtime.contracts import ModelRef, WorkspaceSpec
from app.agent_runtime.semantic_task import (
    SemanticDataDependency,
    SemanticOperation,
    SemanticSubject,
    SemanticTask,
)
from app.agent_runtime.task_graph import compile_task_graph


MODEL = ModelRef(provider_id="test", model_id="test-model")


def test_semantic_task_bounds_oversized_descriptive_intent_without_changing_actions() -> None:
    long_intent = (
        "Inspect port 5432 configuration, compare it with current PostgreSQL "
        "documentation, run the focused configuration test, preserve all prior "
        "investigation context, and report the resulting conclusion with release-note "
        "context while keeping every typed operation exactly as requested."
    )
    task = SemanticTask.model_validate(
        {
            "intent": long_intent,
            "operations": [
                {
                    "kind": "execute",
                    "target": "workspace",
                    "subject_reference": (
                        "src/tests/agent_runtime/test_task_graph_compiler.py"
                    ),
                }
            ],
            "ambiguity": "none",
            "confidence": 1.0,
            "reason_code": "oversized_descriptive_intent",
        }
    )

    assert len(task.intent) == 160
    assert task.intent == long_intent[:160]
    assert len(task.operations) == 1
    assert task.operations[0].kind == "execute"
    assert task.operations[0].target == "workspace"


def test_composite_weather_calendar_compiles_per_node_authority() -> None:
    task = SemanticTask(
        intent="check weather and schedule if appropriate",
        subjects=[
            SemanticSubject(target="weather", reference="Vancouver", kind="location"),
            SemanticSubject(target="calendar", reference="primary calendar"),
        ],
        operations=[
            SemanticOperation(
                kind="read",
                target="weather",
                subject_reference="Vancouver",
            ),
            SemanticOperation(
                kind="read",
                target="calendar",
                subject_reference="primary calendar",
            ),
            SemanticOperation(
                kind="create",
                target="calendar",
                subject_reference="outdoor event",
            ),
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="weather",
                subject_reference="Vancouver",
                freshness="current",
                retrieval_mode="lookup",
            ),
            SemanticDataDependency(
                target="calendar",
                subject_reference="primary calendar",
                freshness="current",
            ),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
        reason_code="weather_calendar_composite",
    )

    compiled = compile_task_graph(
        "Check Vancouver weather and my calendar, then create an outdoor event.",
        task,
        model=MODEL,
    )

    assert compiled.ok is True
    assert compiled.graph is not None
    graph = compiled.graph
    by_profile = {
        node.profile_id: node
        for node in graph.nodes
        if node.profile_id is not None
    }
    research = by_profile["research"]
    assistant = by_profile["personal-assistant"]

    assert research.kind == "evidence_read"
    assert research.required_local_capabilities == []
    assert set(research.required_external_capabilities) == {"weather.current"}
    assert "calendar.create_event" not in research.required_external_capabilities
    assert [
        (scope.capability, scope.resource_type, scope.resource_id)
        for scope in research.resource_scopes
    ] == [("weather.current", "location", "Vancouver")]

    assert "calendar.read_availability" in assistant.required_external_capabilities
    assert "calendar.create_event" in assistant.required_external_capabilities
    assert "weather.current" not in assistant.required_external_capabilities

    assert not hasattr(graph, "capabilities")
    assert any(
        edge.source == research.id
        and edge.target == assistant.id
        and edge.kind == "data"
        for edge in graph.edges
    )
    join = next(node for node in graph.nodes if node.kind == "join")
    assert join.required_local_capabilities == []
    assert join.required_external_capabilities == []
    synthesis = next(node for node in graph.nodes if node.kind == "synthesis")
    assert synthesis.profile_id is None
    assert synthesis.required_local_capabilities == []
    assert synthesis.required_external_capabilities == []


def test_cross_profile_coding_node_cannot_compile_without_workspace() -> None:
    task = SemanticTask(
        intent="fix code and email the result",
        operations=[
            SemanticOperation(kind="modify", target="workspace"),
            SemanticOperation(kind="send", target="email"),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
        reason_code="code_email_composite",
    )

    blocked = compile_task_graph(
        "Fix the code and email the result.",
        task,
        model=MODEL,
    )

    assert blocked.graph is None
    assert any(
        row.code == "required_workspace_unavailable"
        for row in blocked.anomalies
    )

    allowed = compile_task_graph(
        "Fix the code and email the result.",
        task,
        model=MODEL,
        workspace=WorkspaceSpec(
            root="/tmp/omnix",
            repository="/tmp/omnix",
            base_ref="HEAD",
        ),
    )
    assert allowed.ok is True
    assert allowed.graph is not None
    coding = next(
        node for node in allowed.graph.nodes
        if node.profile_id == "coding"
    )
    assistant = next(
        node for node in allowed.graph.nodes
        if node.profile_id == "personal-assistant"
    )
    assert "workspace.edit" in coding.required_local_capabilities
    assert "gmail.send_email" not in coding.required_external_capabilities
    assert assistant.required_local_capabilities == []
    assert "gmail.send_email" in assistant.required_external_capabilities


def test_ambiguous_composite_never_compiles_to_graph_authority() -> None:
    task = SemanticTask(
        intent="do it",
        subjects=[
            SemanticSubject(target="home", reference="it"),
            SemanticSubject(target="calendar", reference="it"),
        ],
        operations=[
            SemanticOperation(kind="modify", target="home"),
            SemanticOperation(kind="create", target="calendar"),
        ],
        ambiguity="clarification_required",
        candidate_interpretations=["home action", "calendar action"],
        reason_code="ambiguous_composite",
    )

    compiled = compile_task_graph("do it", task, model=MODEL)

    assert compiled.graph is None
    assert [row.code for row in compiled.anomalies] == ["clarification_required"]


def test_market_and_weather_do_not_overcollapse_research_authority() -> None:
    task = SemanticTask(
        intent="check market quote and Vancouver weather",
        operations=[
            SemanticOperation(
                kind="read",
                target="market_quote",
                subject_reference="GME",
            ),
            SemanticOperation(
                kind="read",
                target="weather",
                subject_reference="Vancouver",
            ),
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="market_quote",
                subject_reference="GME",
                freshness="current",
                retrieval_mode="lookup",
            ),
            SemanticDataDependency(
                target="weather",
                subject_reference="Vancouver",
                freshness="current",
                retrieval_mode="lookup",
            ),
        ],
        autonomous=True,
        multi_step=False,
        ambiguity="none",
    )

    compiled = compile_task_graph(
        "Check GME and Vancouver weather.",
        task,
        model=MODEL,
    )

    assert compiled.ok is True
    assert compiled.graph is not None
    by_profile = {
        node.profile_id: node
        for node in compiled.graph.nodes
        if node.profile_id in {"trading-research", "research"}
        and node.id != "synthesize-results"
    }
    assert set(by_profile) == {"trading-research", "research"}
    assert "weather.current" in by_profile["research"].required_external_capabilities
    assert "weather.current" not in by_profile["trading-research"].required_external_capabilities


def test_composite_coding_mutation_keeps_diff_and_test_acceptance_floor() -> None:
    task = SemanticTask(
        intent="fix code and email the result",
        operations=[
            SemanticOperation(kind="modify", target="workspace"),
            SemanticOperation(kind="send", target="email"),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
    )

    compiled = compile_task_graph(
        "Fix the code and email the result.",
        task,
        model=MODEL,
        workspace=WorkspaceSpec(
            root="/tmp/omnix",
            repository="/tmp/omnix",
            base_ref="HEAD",
        ),
    )

    assert compiled.ok is True
    assert compiled.graph is not None
    coding = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "coding"
    )
    assert coding.acceptance_plan is not None
    assert coding.acceptance_plan.require_diff is True
    assert coding.acceptance_plan.required_artifacts == ["diff"]
    assert "successful_test_command" in coding.acceptance_plan.checks


def test_multistep_read_to_read_preserves_cross_profile_order() -> None:
    task = SemanticTask(
        intent="research release then compare repository",
        operations=[
            SemanticOperation(
                kind="research",
                target="software_release",
                subject_reference="React",
            ),
            SemanticOperation(
                kind="read",
                target="repository",
                subject_reference="current repository dependencies",
            ),
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="software_release",
                subject_reference="React",
                freshness="current",
                retrieval_mode="lookup",
            ),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
    )
    compiled = compile_task_graph(
        "Research the React release, then compare it with this repository.",
        task,
        model=MODEL,
        workspace=WorkspaceSpec(
            root="/tmp/omnix",
            repository="/tmp/omnix",
            base_ref="HEAD",
        ),
    )

    assert compiled.ok is True
    assert compiled.graph is not None
    research = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "research" and node.id != "synthesize-results"
    )
    coding = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "coding"
    )
    assert any(
        edge.source == research.id
        and edge.target == coding.id
        and edge.kind == "data"
        and edge.source_output == "result"
        for edge in compiled.graph.edges
    )
    assert compiled.graph.output_contract["result_node"] == "synthesize-results"
    synthesis = next(
        node for node in compiled.graph.nodes
        if node.id == "synthesize-results"
    )
    assert synthesis.required_local_capabilities == []
    assert synthesis.required_external_capabilities == []


def test_read_only_weather_revisit_is_hoisted_before_terminal_calendar_action() -> None:
    task = SemanticTask(
        intent="check Vancouver and Seattle weather before creating calendar event",
        operations=[
            SemanticOperation(kind="read", target="weather", subject_reference="Vancouver"),
            SemanticOperation(kind="read", target="calendar", subject_reference="primary calendar"),
            SemanticOperation(kind="create", target="calendar", subject_reference="Saturday walk"),
            SemanticOperation(kind="read", target="weather", subject_reference="Seattle"),
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="weather",
                subject_reference="Vancouver",
                freshness="current",
                retrieval_mode="lookup",
            ),
            SemanticDataDependency(
                target="weather",
                subject_reference="Seattle",
                freshness="current",
                retrieval_mode="lookup",
            ),
            SemanticDataDependency(
                target="calendar",
                subject_reference="primary calendar",
                freshness="current",
            ),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
    )

    compiled = compile_task_graph(
        "Check Vancouver weather and my calendar, then also check Seattle weather "
        "before creating the event.",
        task,
        model=MODEL,
    )

    assert compiled.ok is True
    assert compiled.graph is not None
    research = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "research"
    )
    assistant = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "personal-assistant"
    )
    assert any(
        edge.source == research.id
        and edge.target == assistant.id
        and edge.kind == "data"
        for edge in compiled.graph.edges
    )


def test_read_only_market_revisit_is_hoisted_before_terminal_email_action() -> None:
    task = SemanticTask(
        intent="combine GME AMC and weather in one email",
        operations=[
            SemanticOperation(kind="read", target="market_quote", subject_reference="GME"),
            SemanticOperation(kind="read", target="weather", subject_reference="Vancouver"),
            SemanticOperation(kind="send", target="email", subject_reference="combined summary"),
            SemanticOperation(kind="read", target="market_quote", subject_reference="AMC"),
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="market_quote",
                subject_reference="GME",
                freshness="current",
                retrieval_mode="lookup",
            ),
            SemanticDataDependency(
                target="market_quote",
                subject_reference="AMC",
                freshness="current",
                retrieval_mode="lookup",
            ),
            SemanticDataDependency(
                target="weather",
                subject_reference="Vancouver",
                freshness="current",
                retrieval_mode="lookup",
            ),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
    )

    compiled = compile_task_graph(
        "Check GME, Vancouver weather, and AMC, then email one combined summary.",
        task,
        model=MODEL,
    )

    assert compiled.ok is True
    assert compiled.graph is not None
    trading = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "trading-research"
    )
    research = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "research"
    )
    assistant = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "personal-assistant"
    )
    assert any(
        edge.source == trading.id and edge.target == research.id
        for edge in compiled.graph.edges
    )
    assert any(
        edge.source == research.id and edge.target == assistant.id
        for edge in compiled.graph.edges
    )


def test_terminal_personal_assistant_revisit_moves_after_read_only_additions() -> None:
    task = SemanticTask(
        intent="weather calendar market repo then final email",
        operations=[
            SemanticOperation(kind="read", target="weather", subject_reference="Vancouver"),
            SemanticOperation(kind="read", target="calendar", subject_reference="primary calendar"),
            SemanticOperation(kind="create", target="calendar", subject_reference="outdoor meeting"),
            SemanticOperation(kind="read", target="market_quote", subject_reference="AAPL"),
            SemanticOperation(kind="inspect", target="repository", subject_reference="TaskGraph API"),
            SemanticOperation(kind="send", target="email", subject_reference="final combined result"),
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="weather",
                subject_reference="Vancouver",
                freshness="current",
                retrieval_mode="lookup",
            ),
            SemanticDataDependency(
                target="market_quote",
                subject_reference="AAPL",
                freshness="current",
                retrieval_mode="lookup",
            ),
            SemanticDataDependency(
                target="calendar",
                subject_reference="primary calendar",
                freshness="current",
            ),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
    )

    compiled = compile_task_graph(
        "Check weather/calendar, include AAPL and inspect the repo, then email the final result.",
        task,
        model=MODEL,
        workspace=WorkspaceSpec(
            root="/tmp/omnix",
            repository="/tmp/omnix",
            base_ref="HEAD",
        ),
    )

    assert compiled.ok is True
    assert compiled.graph is not None
    assistant = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "personal-assistant"
    )
    predecessors = {
        edge.source
        for edge in compiled.graph.edges
        if edge.target == assistant.id
    }
    assert predecessors
    assert any(
        node.profile_id == "coding" and node.id in predecessors
        for node in compiled.graph.nodes
    )


def test_interleaved_profiles_compile_as_least_privilege_segments() -> None:
    task = SemanticTask(
        intent="read repo research release then modify repo",
        operations=[
            SemanticOperation(kind="read", target="repository"),
            SemanticOperation(kind="research", target="software_release"),
            SemanticOperation(kind="modify", target="workspace"),
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="software_release",
                subject_reference="React",
                freshness="current",
                retrieval_mode="lookup",
            )
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
    )
    compiled = compile_task_graph(
        "Inspect the repo, research the React release, then modify the repo.",
        task,
        model=MODEL,
        workspace=WorkspaceSpec(
            root="/tmp/omnix",
            repository="/tmp/omnix",
            base_ref="HEAD",
        ),
    )

    assert compiled.ok is True
    assert compiled.graph is not None
    coding_nodes = [
        node for node in compiled.graph.nodes
        if node.profile_id == "coding"
    ]
    assert len(coding_nodes) == 2
    first_coding, second_coding = coding_nodes
    research = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "research"
    )

    assert first_coding.semantic_action_intents == ["workspace_read"]
    assert "workspace_mutate" not in first_coding.semantic_action_intents
    assert "workspace_mutate" in second_coding.semantic_action_intents
    assert second_coding.acceptance_plan is not None
    assert second_coding.acceptance_plan.require_diff is True

    assert any(
        edge.source == first_coding.id
        and edge.target == research.id
        and edge.kind == "data"
        for edge in compiled.graph.edges
    )
    assert any(
        edge.source == research.id
        and edge.target == second_coding.id
        and edge.kind == "data"
        for edge in compiled.graph.edges
    )


def test_completed_coding_phase_can_feed_deferred_email_without_interleaving() -> None:
    task = SemanticTask(
        intent="fix test validate then email result",
        operations=[
            SemanticOperation(kind="modify", target="workspace"),
            SemanticOperation(kind="execute", target="workspace"),
            SemanticOperation(kind="send", target="email"),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
    )
    compiled = compile_task_graph(
        "Fix the failing test, run the focused tests, then email me the final result.",
        task,
        model=MODEL,
        workspace=WorkspaceSpec(
            root="/tmp/omnix",
            repository="/tmp/omnix",
            base_ref="HEAD",
        ),
    )

    assert compiled.ok is True
    assert compiled.graph is not None
    coding = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "coding"
    )
    assistant = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "personal-assistant"
    )
    assert any(
        edge.source == coding.id
        and edge.target == assistant.id
        and edge.kind == "data"
        for edge in compiled.graph.edges
    )
    assert coding.acceptance_plan is not None
    assert "successful_test_command" in coding.acceptance_plan.checks


def test_single_step_cross_profile_request_preserves_operation_dependency() -> None:
    task = SemanticTask(
        intent="email the AAPL price",
        operations=[
            SemanticOperation(
                kind="read",
                target="market_quote",
                subject_reference="AAPL",
            ),
            SemanticOperation(
                kind="send",
                target="email",
                subject_reference="AAPL price",
            ),
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="market_quote",
                subject_reference="AAPL",
                freshness="current",
                retrieval_mode="lookup",
            )
        ],
        autonomous=True,
        multi_step=False,
        ambiguity="none",
    )
    compiled = compile_task_graph(
        "Email me AAPL's price.",
        task,
        model=MODEL,
    )
    assert compiled.ok is True
    assert compiled.graph is not None
    market = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "trading-research"
    )
    email = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "personal-assistant"
    )
    assert any(
        edge.source == market.id
        and edge.target == email.id
        and edge.kind == "data"
        for edge in compiled.graph.edges
    )


def test_task_graph_carries_bounded_chat_reference_context() -> None:
    task = SemanticTask(
        intent="research release and email it",
        operations=[
            SemanticOperation(kind="research", target="software_release"),
            SemanticOperation(kind="send", target="email"),
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
    )
    compiled = compile_task_graph(
        "Research the release and email it.",
        task,
        model=MODEL,
        reference_context="Earlier confirmed context",
    )
    assert compiled.ok is True
    assert compiled.graph is not None
    assert compiled.graph.reference_context == "Earlier confirmed context"
