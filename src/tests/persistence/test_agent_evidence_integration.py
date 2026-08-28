from __future__ import annotations

import os
import uuid

import pytest

from app.agent_runtime.contracts import (
    AgentRunCommand,
    AgentRunSpec,
    EvidenceDecision,
    EvidencePolicy,
    EvidenceReceipt,
    EvidenceRequirement,
    ModelRef,
    TaskRevision,
)
from app.agent_runtime.repository import PostgresAgentRunRepository
from app.agent_runtime.service import AgentRunService
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-agent-evidence-tests",
        )
    )


def test_task_revisions_and_evidence_receipts_are_durable_and_recomputable() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"evidence-{uuid.uuid4().hex}"
        policy = EvidencePolicy(
            requirement="required",
            requirements=[
                EvidenceRequirement(
                    id="web",
                    source_class="general_current_web",
                    freshness="current",
                    trust_floor="reputable",
                    max_age_seconds=86400,
                )
            ],
        )
        spec = AgentRunSpec(
            run_id=run_id,
            task="latest topic",
            profile="research",
            model=ModelRef(provider_id="test", model_id="model"),
            external_capabilities=["research.web_search"],
            evidence_policy=policy,
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            repository.create_run(spec)
            first = repository.latest_task_revision(run_id)
            assert first is not None
            revision = TaskRevision(
                run_id=run_id,
                sequence=2,
                previous_revision_id=first.revision_id,
                source_command_id="steer-1",
                user_instruction="focus on today",
                effective_objective="latest topic today",
                evidence_decision=EvidenceDecision(
                    policy=policy,
                    confidence=0.98,
                    reason="required:general_current_web",
                ),
                required_external_capabilities=["research.web_search"],
            )
            repository.add_task_revision(revision)
            repository.add_evidence_receipt(
                EvidenceReceipt(
                    run_id=run_id,
                    task_revision_id=revision.revision_id,
                    capability_id="research.web_search",
                    source_class="general_current_web",
                    request_digest="request",
                    provider="test",
                    source_manifest_id="manifest-1",
                    source_count=2,
                    trust_level="reputable",
                    result_digest="result",
                )
            )
            work.commit()

        service = AgentRunService(database, worker_id="evidence-reader")
        service._supervisor_started = True
        revisions = service.task_revisions(run_id)
        receipts = service.evidence_receipts(run_id)
        evidence_set = service.evidence_set(run_id)
        assert [row.sequence for row in revisions] == [1, 2]
        assert len(receipts) == 1
        assert evidence_set.passed
        assert evidence_set.source_manifest_ids == ["manifest-1"]
    finally:
        database.close()


def test_receipt_rolls_back_with_local_capability_transaction() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"rollback-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="topic",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            repository.create_run(spec)
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            repository.add_evidence_receipt(
                EvidenceReceipt(
                    run_id=run_id,
                    capability_id="research.web_search",
                    source_class="general_current_web",
                    request_digest="request",
                    trust_level="reputable",
                    result_digest="result",
                )
            )
            work.rollback()

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            assert repository.list_evidence_receipts(run_id) == []
            work.rollback()
    finally:
        database.close()


def test_steering_compiler_narrows_in_run_and_widens_via_superseding_spec() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"steer-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Research TCP",
            objective="Research TCP",
            profile="research",
            model=ModelRef(provider_id="test", model_id="model"),
            external_capabilities=["research.web_search"],
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            snapshot = repository.create_run(spec)
            work.commit()

        service = AgentRunService(database, worker_id="steering-compiler")
        service._supervisor_started = True
        narrowing = service._compile_steering(
            snapshot,
            AgentRunCommand(
                run_id=run_id,
                command_type="steer",
                payload={"message": "Actually explain TCP congestion control conceptually"},
                idempotency_key="narrow",
            ),
        )
        assert narrowing["superseding_spec"] is None
        assert narrowing["revision"].required_external_capabilities == []

        model_only_id = f"steer-model-{uuid.uuid4().hex}"
        model_only = AgentRunSpec(
            run_id=model_only_id,
            task="Explain TCP",
            objective="Explain TCP",
            profile="research",
            model=ModelRef(provider_id="test", model_id="model"),
            external_capabilities=[],
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            model_snapshot = repository.create_run(model_only)
            work.commit()

        widening = service._compile_steering(
            model_snapshot,
            AgentRunCommand(
                run_id=model_only_id,
                command_type="steer",
                payload={"message": "Actually tell me the latest PostgreSQL release"},
                idempotency_key="widen",
            ),
        )
        replacement = widening["superseding_spec"]
        assert replacement is not None
        assert replacement.supersedes_run_id == model_only_id
        assert replacement.external_capabilities == ["research.web_search"]
    finally:
        database.close()


def test_task_revision_source_command_is_idempotent() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"revision-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Inspect",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            repository.create_run(spec)
            first = repository.latest_task_revision(run_id)
            assert first is not None
            revision = TaskRevision(
                revision_id="stable-revision",
                run_id=run_id,
                sequence=2,
                previous_revision_id=first.revision_id,
                source_command_id="same-command",
                user_instruction="focus",
                effective_objective="focus",
            )
            one = repository.add_task_revision(revision)
            two = repository.add_task_revision(
                revision.model_copy(update={"revision_id": "different-revision"})
            )
            assert one.revision_id == two.revision_id
            assert len(repository.list_task_revisions(run_id)) == 2
            work.rollback()
    finally:
        database.close()
