from __future__ import annotations

import os
import uuid

import pytest

from app.agent_runtime.contracts import ModelRef
from app.agent_runtime.task_graph import (
    TaskGraph,
    TaskNode,
    task_node_fingerprint,
)
from app.agent_runtime.task_graph_repository import (
    PostgresTaskGraphRepository,
    TaskGraphConcurrencyError,
)
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
            application_name="omnix-task-graph-tests",
        )
    )


def test_task_graph_revision_rejects_stale_child_completion_and_claim() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"task-graph-{uuid.uuid4().hex}"
        original_node = TaskNode(
            id="research",
            kind="agent",
            profile_id="research",
            objective="Research the original target.",
            model=MODEL,
        )
        original_graph = TaskGraph(
            graph_id=f"graph-{uuid.uuid4().hex}",
            revision=1,
            user_request_digest="request-v1",
            nodes=[original_node],
            output_contract={"result_node": "research"},
        )

        with unit_of_work(database) as work:
            repository = PostgresTaskGraphRepository(
                work.connection,
                context,
            )
            repository.create_run(original_graph, run_id=run_id)
            original_claim = repository.claim_node(
                run_id,
                original_node.id,
                child_run_id="old-child",
                expected_fingerprint=task_node_fingerprint(original_node),
                expected_graph_revision=1,
            )
            assert original_claim is not None
            assert original_claim.status == "ready"
            work.commit()

        revised_node = original_node.model_copy(
            update={"objective": "Research only the revised target."}
        )
        revised_graph = original_graph.model_copy(
            update={
                "revision": 2,
                "user_request_digest": "request-v2",
                "nodes": [revised_node],
            }
        )

        with unit_of_work(database) as work:
            repository = PostgresTaskGraphRepository(
                work.connection,
                context,
            )
            revised = repository.apply_revision(
                run_id,
                revised_graph,
                user_instruction="Use the revised target instead.",
                reusable_node_ids=set(),
            )
            state = next(
                item
                for item in revised.node_states
                if item.node_id == revised_node.id
            )
            assert state.status == "pending"
            assert state.child_run_id is None
            assert state.fingerprint == task_node_fingerprint(revised_node)
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresTaskGraphRepository(
                work.connection,
                context,
            )
            stale_completion = repository.update_node(
                run_id,
                original_node.id,
                status="completed",
                output={"result": "STALE"},
                expected_fingerprint=task_node_fingerprint(original_node),
                expected_child_run_id="old-child",
                match_child_run_id=True,
                expected_statuses=("ready",),
                expected_graph_revision=1,
            )
            assert stale_completion is None

            stale_claim = repository.claim_node(
                run_id,
                original_node.id,
                child_run_id="another-old-child",
                expected_fingerprint=task_node_fingerprint(original_node),
                expected_graph_revision=1,
            )
            assert stale_claim is None

            current = repository.get_run(run_id)
            assert current is not None
            current_state = next(
                item
                for item in current.node_states
                if item.node_id == revised_node.id
            )
            assert current_state.status == "pending"
            assert current_state.output == {}
            work.rollback()

        with unit_of_work(database) as work:
            repository = PostgresTaskGraphRepository(
                work.connection,
                context,
            )
            current_claim = repository.claim_node(
                run_id,
                revised_node.id,
                child_run_id="new-child",
                expected_fingerprint=task_node_fingerprint(revised_node),
                expected_graph_revision=2,
            )
            assert current_claim is not None
            completed = repository.update_node(
                run_id,
                revised_node.id,
                status="completed",
                output={"result": "fresh result"},
                expected_fingerprint=current_claim.fingerprint,
                expected_child_run_id="new-child",
                match_child_run_id=True,
                expected_statuses=("ready",),
                expected_graph_revision=2,
            )
            assert completed is not None
            persisted = repository.get_run(run_id)
            assert persisted is not None
            assert persisted.result == "fresh result"
            work.commit()
    finally:
        database.close()


def test_task_graph_batch_claim_metadata_is_durable() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"task-graph-batch-{uuid.uuid4().hex}"
        node = TaskNode(
            id="release",
            kind="agent",
            profile_id="research",
            objective="Research release.",
            model=MODEL,
        )
        graph = TaskGraph(
            user_request_digest="batch-request",
            nodes=[node],
        )
        descriptor = {
            "evidence_batch": {
                "batch_id": "batch-1",
                "node_ids": ["release"],
                "leader_id": "release",
            }
        }

        with unit_of_work(database) as work:
            repository = PostgresTaskGraphRepository(
                work.connection,
                context,
            )
            repository.create_run(graph, run_id=run_id)
            claimed = repository.claim_node(
                run_id,
                node.id,
                child_run_id="shared-child",
                claim_output=descriptor,
                expected_fingerprint=task_node_fingerprint(node),
                expected_graph_revision=1,
            )
            assert claimed is not None
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresTaskGraphRepository(
                work.connection,
                context,
            )
            persisted = repository.get_run(run_id)
            assert persisted is not None
            state = persisted.node_states[0]
            assert state.child_run_id == "shared-child"
            assert state.output == descriptor
            work.rollback()
    finally:
        database.close()


@pytest.mark.parametrize("terminal_status", ["completed", "failed", "cancelled"])
def test_terminal_task_graph_cannot_be_revised_or_resurrected(
    terminal_status: str,
) -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"task-graph-terminal-{uuid.uuid4().hex}"
        node = TaskNode(
            id="research",
            kind="agent",
            profile_id="research",
            objective="Research once.",
            model=MODEL,
        )
        graph = TaskGraph(
            graph_id=f"graph-{uuid.uuid4().hex}",
            revision=1,
            user_request_digest="request-v1",
            nodes=[node],
        )

        with unit_of_work(database) as work:
            repository = PostgresTaskGraphRepository(
                work.connection,
                context,
            )
            repository.create_run(graph, run_id=run_id)
            repository.update_run_status(
                run_id,
                terminal_status,
                last_error=(
                    "terminal test"
                    if terminal_status != "completed"
                    else None
                ),
            )
            work.commit()

        revised = graph.model_copy(
            update={
                "revision": 2,
                "user_request_digest": "request-v2",
                "nodes": [
                    node.model_copy(
                        update={"objective": "Do not resurrect this graph."}
                    )
                ],
            }
        )

        with unit_of_work(database) as work:
            repository = PostgresTaskGraphRepository(
                work.connection,
                context,
            )
            with pytest.raises(
                TaskGraphConcurrencyError,
                match="cannot revise terminal task graph",
            ):
                repository.apply_revision(
                    run_id,
                    revised,
                    user_instruction="also do something",
                    reusable_node_ids=set(),
                )
            work.rollback()

        with unit_of_work(database) as work:
            repository = PostgresTaskGraphRepository(
                work.connection,
                context,
            )
            persisted = repository.get_run(run_id)
            assert persisted is not None
            assert persisted.status == terminal_status
            assert persisted.graph.revision == 1
            work.rollback()
    finally:
        database.close()


def test_stale_run_status_cas_cannot_resurrect_cancelled_graph() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"task-graph-status-cas-{uuid.uuid4().hex}"
        node = TaskNode(
            id="research",
            kind="agent",
            profile_id="research",
            objective="Research once.",
            model=MODEL,
        )
        graph = TaskGraph(
            graph_id=f"graph-{uuid.uuid4().hex}",
            revision=1,
            user_request_digest="request",
            nodes=[node],
        )

        with unit_of_work(database) as work:
            repository = PostgresTaskGraphRepository(work.connection, context)
            initial = repository.create_run(graph, run_id=run_id)
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresTaskGraphRepository(work.connection, context)
            cancelled = repository.update_run_status(
                run_id,
                "cancelled",
                last_error="cancelled_by_user",
                expected_revision=initial.revision,
                expected_graph_revision=graph.revision,
                expected_statuses=(initial.status,),
            )
            assert cancelled is not None
            assert cancelled.status == "cancelled"
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresTaskGraphRepository(work.connection, context)
            stale = repository.update_run_status(
                run_id,
                "running",
                expected_revision=initial.revision,
                expected_graph_revision=graph.revision,
                expected_statuses=(initial.status,),
            )
            assert stale is None
            persisted = repository.get_run(run_id)
            assert persisted is not None
            assert persisted.status == "cancelled"
            assert persisted.last_error == "cancelled_by_user"
            work.rollback()
    finally:
        database.close()
