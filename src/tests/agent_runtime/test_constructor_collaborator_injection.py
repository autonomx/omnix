from __future__ import annotations

from app.platform.agent_runtime.contracts import AgentEvent
from app.platform.agent_runtime.pi_runtime import PiAgentRuntime, normalize_pi_event, pi_rpc_argv
from app.platform.agent_runtime.service import AgentRunService


def test_agent_run_service_stores_constructor_injected_ports() -> None:
    unit_of_work = lambda *_args, **_kwargs: None
    repository_factory = lambda *_args, **_kwargs: None
    quality_repository_factory = lambda *_args, **_kwargs: None
    workspace_authority_factory = lambda *_args, **_kwargs: None
    semantic_task_parser = lambda *_args, **_kwargs: None
    terminal_reviewer_consumer = lambda *_args, **_kwargs: None

    service = AgentRunService(
        object(),
        unit_of_work_fn=unit_of_work,
        repository_factory=repository_factory,
        quality_repository_factory=quality_repository_factory,
        workspace_authority_factory=workspace_authority_factory,
        semantic_task_parser=semantic_task_parser,
        terminal_reviewer_consumer=terminal_reviewer_consumer,
    )

    assert service.unit_of_work is unit_of_work
    assert service.repository_factory is repository_factory
    assert service.quality_repository_factory is quality_repository_factory
    assert service.workspace_authority_factory is workspace_authority_factory
    assert service.semantic_task_parser is semantic_task_parser
    assert service.terminal_reviewer_consumer is terminal_reviewer_consumer


def test_pi_runtime_stores_constructor_injected_ports() -> None:
    argv_builder = lambda *_args, **_kwargs: []
    event_normalizer = lambda *_args, **_kwargs: AgentEvent(
        run_id="run-1",
        event_type="injected",
    )

    runtime = PiAgentRuntime(
        argv_builder=argv_builder,
        event_normalizer=event_normalizer,
    )

    assert runtime.argv_builder is argv_builder
    assert runtime.event_normalizer is event_normalizer
    assert callable(pi_rpc_argv)
    assert callable(normalize_pi_event)
