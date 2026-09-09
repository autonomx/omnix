from __future__ import annotations

import os
import uuid

import pytest

from app.agent_runtime.contracts import AgentRunSpec, ModelRef
from app.agent_runtime.repository import PostgresAgentRunRepository
from app.agent_runtime.task_graph import TaskGraph, TaskNode, task_node_fingerprint
from app.agent_runtime.task_graph_repository import PostgresTaskGraphRepository
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
MODEL = ModelRef(provider_id="test", model_id="test-model")


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-task-graph-revocation-tests",
        )
    )


def _create_running_child(repository: PostgresAgentRunRepository, run_id: str) -> None:
    snapshot = repository.create_run(
        AgentRunSpec(
            run_id=run_id,
            task="Research only.",
            objective="Research only.",
            profile="research",
            model=MODEL,
        )
    )
    repository.update_state(
        run_id,
        expected_revision=snapshot.revision,
        status="running",
    )


def test_revision_revokes_invalidated_child_before_current_identity_is_cleared() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        graph_run_id = f"graph-{uuid.uuid4().hex}"
        child_run_id = f"child-{uuid.uuid4().hex}"
        node = TaskNode(
            id="research",
            kind="agent",
            profile_id="research",
            objective="Research the original target.",
            model=MODEL,
        )
        graph = TaskGraph(
            graph_id=f"graph-contract-{uuid.uuid4().hex}",
            revision=1,
            user_request_digest="v1",
            nodes=[node],
        )
        with unit_of_work(database) as work:
            graph_repository = PostgresTaskGraphRepository(work.connection, context)
            agent_repository = PostgresAgentRunRepository(work.connection, context)
            graph_repository.create_run(graph, run_id=graph_run_id)
            _create_running_child(agent_repository, child_run_id)
            claimed = graph_repository.claim_node(
                graph_run_id,
                node.id,
                child_run_id=child_run_id,
                expected_fingerprint=task_node_fingerprint(node),
                expected_graph_revision=1,
            )
            assert claimed is not None
            work.commit()

        revised_node = node.model_copy(update={"objective": "Research a different target."})
        revised_graph = graph.model_copy(
            update={"revision": 2, "user_request_digest": "v2", "nodes": [revised_node]}
        )
        with unit_of_work(database) as work:
            graph_repository = PostgresTaskGraphRepository(work.connection, context)
            agent_repository = PostgresAgentRunRepository(work.connection, context)
            graph_repository.apply_revision(
                graph_run_id,
                revised_graph,
                user_instruction="Use the different target.",
                reusable_node_ids=set(),
            )
            child = agent_repository.get_run(child_run_id)
            assert child is not None
            assert child.status == "cancel_requested"
            assert child.desired_state == "cancelled"
            current = graph_repository.get_run(graph_run_id)
            assert current is not None
            state = next(item for item in current.node_states if item.node_id == node.id)
            assert state.child_run_id is None
            work.commit()
    finally:
        database.close()


def test_node_cancellation_revokes_child_authority_before_process_cleanup() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        graph_run_id = f"graph-{uuid.uuid4().hex}"
        child_run_id = f"child-{uuid.uuid4().hex}"
        node = TaskNode(
            id="research",
            kind="agent",
            profile_id="research",
            objective="Research target.",
            model=MODEL,
        )
        graph = TaskGraph(
            graph_id=f"graph-contract-{uuid.uuid4().hex}",
            revision=1,
            user_request_digest="request",
            nodes=[node],
        )
        with unit_of_work(database) as work:
            graph_repository = PostgresTaskGraphRepository(work.connection, context)
            agent_repository = PostgresAgentRunRepository(work.connection, context)
            graph_repository.create_run(graph, run_id=graph_run_id)
            _create_running_child(agent_repository, child_run_id)
            claimed = graph_repository.claim_node(
                graph_run_id,
                node.id,
                child_run_id=child_run_id,
                expected_fingerprint=task_node_fingerprint(node),
                expected_graph_revision=1,
            )
            assert claimed is not None
            cancelled = graph_repository.update_node(
                graph_run_id,
                node.id,
                status="cancelled",
                last_error="cancelled_by_user",
                expected_fingerprint=claimed.fingerprint,
                expected_child_run_id=child_run_id,
                match_child_run_id=True,
                expected_statuses=("ready",),
                expected_graph_revision=1,
            )
            assert cancelled is not None
            child = agent_repository.get_run(child_run_id)
            assert child is not None
            assert child.status == "cancel_requested"
            assert child.desired_state == "cancelled"
            work.commit()
    finally:
        database.close()
