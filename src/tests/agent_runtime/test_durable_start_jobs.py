from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agent_runtime.contracts import AgentRunSnapshot, AgentRunSpec, ModelRef
from app.agent_runtime.jobs import (
    AGENT_RUN_JOB_HANDLERS,
    AgentRunJobInput,
    create_agent_promote_request,
    create_agent_run_start_request,
    create_agent_workspace_prepare_request,
)
from app.agent_runtime.service_core import AgentRunService
from app.jobs.handlers import JobExecutionContext, JobHandlerRegistry


def test_agent_start_job_contracts_are_registered_and_typed() -> None:
    registry = JobHandlerRegistry(AGENT_RUN_JOB_HANDLERS)

    assert registry.types() == (
        "agent.promote",
        "agent.run.start",
        "agent.workspace.prepare",
    )
    assert registry.require("agent.workspace.prepare").input_model is AgentRunJobInput
    assert registry.require("agent.run.start").input_model is AgentRunJobInput
    assert create_agent_workspace_prepare_request("run-1").input_payload == {"run_id": "run-1"}
    assert create_agent_run_start_request("run-1").input_payload == {"run_id": "run-1"}


def test_workspace_prepare_handler_chains_the_durable_start_job() -> None:
    jobs = MagicMock()
    jobs.complete_job.return_value = None
    service = SimpleNamespace(
        prepare_workspace_job=MagicMock(return_value=SimpleNamespace(status="queued"))
    )
    context = JobExecutionContext(
        job_store=jobs,
        services=SimpleNamespace(agent_runs=service, jobs=jobs),
    )
    job = SimpleNamespace(id="job-prepare", input_payload={"run_id": "run-2"})
    handler = JobHandlerRegistry(AGENT_RUN_JOB_HANDLERS).require(
        "agent.workspace.prepare"
    ).handler

    assert handler(context, job) is job
    service.prepare_workspace_job.assert_called_once_with(
        "run-2",
        job_store=jobs,
        reference_session_id=None,
        reference_message_id=None,
        reference_message_ids=None,
        task_graph_run_id=None,
        task_graph_node_ids=None,
    )
    jobs.complete_job.assert_called_once()
    assert jobs.complete_job.call_args.args[0] == job.id
    output = jobs.complete_job.call_args.args[1].output_refs[0]
    assert output == {
        "kind": "agent_run",
        "stage": "workspace_prepared",
        "run_id": "run-2",
        "run_status": "queued",
    }


def test_agent_run_start_handler_completes_after_starting_pi() -> None:
    jobs = MagicMock()
    jobs.complete_job.return_value = None
    snapshot = AgentRunSnapshot(
        run_id="run-2",
        spec=AgentRunSpec(
            run_id="run-2",
            task="research a design",
            profile="research",
            model=ModelRef(provider_id="test", model_id="model"),
        ),
        status="running",
    )
    service = SimpleNamespace(start_prepared_run=MagicMock(return_value=snapshot))
    context = JobExecutionContext(
        job_store=jobs,
        services=SimpleNamespace(agent_runs=service, jobs=jobs, chat=None),
    )
    job = SimpleNamespace(id="job-start", input_payload={"run_id": "run-2"})
    handler = JobHandlerRegistry(AGENT_RUN_JOB_HANDLERS).require(
        "agent.run.start"
    ).handler

    assert handler(context, job) is job

    service.start_prepared_run.assert_called_once_with(
        "run-2",
        reference_context="",
        reference_images=None,
    )
    completed = jobs.complete_job.call_args.args[1]
    assert completed.output_refs == [{
        "kind": "agent_run",
        "stage": "runtime_started",
        "run_id": "run-2",
        "run_status": "running",
    }]


def test_promote_handler_runs_acceptance_through_the_durable_service() -> None:
    jobs = MagicMock()
    jobs.complete_job.return_value = None
    promoted = AgentRunSnapshot(
        run_id="run-4",
        spec=AgentRunSpec(
            run_id="run-4",
            task="research a design",
            profile="research",
            model=ModelRef(provider_id="test", model_id="model"),
        ),
        status="completed",
    )
    service = SimpleNamespace(process_promote_job=MagicMock(return_value=promoted))
    context = JobExecutionContext(
        job_store=jobs,
        services=SimpleNamespace(agent_runs=service),
    )
    request = create_agent_promote_request("run-4", trigger_id="settled-4")
    job = SimpleNamespace(id="job-promote", input_payload=request.input_payload)
    handler = JobHandlerRegistry(AGENT_RUN_JOB_HANDLERS).require("agent.promote").handler

    assert handler(context, job) is job
    service.process_promote_job.assert_called_once_with("run-4")
    assert jobs.complete_job.call_args.args[1].output_refs == [{
        "kind": "agent_run",
        "stage": "promoted",
        "run_id": "run-4",
        "run_status": "completed",
    }]


def test_http_submission_persists_and_enqueues_without_preparing_or_spawning() -> None:
    spec = AgentRunSpec(
        run_id="run-3",
        task="research a design",
        profile="research",
        model=ModelRef(provider_id="test", model_id="model"),
    )
    snapshot = AgentRunSnapshot(run_id=spec.run_id, spec=spec)
    repository = SimpleNamespace(create_run=MagicMock(return_value=snapshot))

    class Work:
        connection = object()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            return None

    service = object.__new__(AgentRunService)
    service.database = object()
    service.context = object()
    service.unit_of_work = lambda _database: Work()
    service.repository_factory = lambda _connection, _context: repository
    service._prepare_start_spec = lambda value: value
    service._validate_run_spec_authority = lambda _spec: None
    service._validate_evidence_authority = lambda _spec: None
    service._prepare_workspace = MagicMock(side_effect=AssertionError("request prepared workspace"))
    service.runtime = SimpleNamespace(start=MagicMock(side_effect=AssertionError("request spawned Pi")))
    job_store = MagicMock()

    result = service.submit_start(spec, job_store=job_store)

    assert result.status == "queued"
    repository.create_run.assert_called_once_with(spec)
    job_store.create_job_once.assert_called_once()
    request = job_store.create_job_once.call_args.args[0]
    assert request.type == "agent.workspace.prepare"
    assert request.input_payload == {"run_id": spec.run_id}
    service._prepare_workspace.assert_not_called()
    service.runtime.start.assert_not_called()
