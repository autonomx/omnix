from __future__ import annotations

import os
import uuid

import pytest

from app.agent_runtime.coding_quality_repository import PostgresCodingQualityRepository
from app.agent_runtime.contracts import (
    AgentRunSpec,
    ModelRef,
    ReviewResult,
    ReviewSnapshot,
    ValidationResult,
    WorkspaceState,
)
from app.agent_runtime.repository import PostgresAgentRunRepository
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-coding-quality-tests",
        )
    )


def test_coding_quality_state_and_evidence_survive_repository_reconstruction() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"quality-{uuid.uuid4().hex}"
        revision_id = f"revision-{uuid.uuid4().hex}"
        state = WorkspaceState(
            state_id=f"state-{uuid.uuid4().hex}",
            run_id=run_id,
            task_revision_id=revision_id,
            base_commit_sha="a" * 40,
            tracked_diff_sha256="b" * 64,
            untracked_file_manifest_sha256="c" * 64,
            modified_paths=["src/app/example.py"],
        )
        validation = ValidationResult(
            run_id=run_id,
            validation_id="final-state-tests",
            kind="test",
            task_revision_id=revision_id,
            workspace_state_id=state.state_id,
            command="python -m pytest tests/test_example.py -q",
            exit_code=0,
            success=True,
            output_digest="d" * 64,
        )
        review_snapshot = ReviewSnapshot(
            run_id=run_id,
            task_revision_id=revision_id,
            workspace_state_id=state.state_id,
            base_commit_sha=state.base_commit_sha,
            patch_checksum=state.state_id,
            workspace_root="/tmp/immutable-review",
            validation_result_ids=[validation.result_id],
        )
        review = ReviewResult(
            run_id=run_id,
            reviewer_run_id=f"reviewer-{uuid.uuid4().hex}",
            review_snapshot_id=review_snapshot.snapshot_id,
            task_revision_id=revision_id,
            workspace_state_id=state.state_id,
            verdict="approve",
        )

        with unit_of_work(database) as work:
            run_repository = PostgresAgentRunRepository(work.connection, context)
            run_repository.create_run(
                AgentRunSpec(
                    run_id=run_id,
                    task="Implement the quality fixture",
                    objective="Implement the quality fixture",
                    profile="coding",
                    model=ModelRef(provider_id="test", model_id="test-model"),
                    quality_policy="strict",
                )
            )
            quality = PostgresCodingQualityRepository(work.connection, context)
            quality.set_stage(
                run_id,
                stage="reviewing",
                attempt=2,
                task_revision_id=revision_id,
                workspace_state_id=state.state_id,
            )
            quality.add_workspace_state(state)
            quality.add_validation_result(validation)
            quality.add_review_snapshot(review_snapshot)
            quality.add_review_result(review)
            work.commit()

        # A new UoW/repository pair represents a new service/worker process: no
        # in-memory quality state participates in this readback.
        with unit_of_work(database) as work:
            quality = PostgresCodingQualityRepository(work.connection, context)
            stage = quality.get_stage(run_id)
            persisted_state = quality.get_workspace_state(run_id, state.state_id)
            validations = quality.list_validation_results(
                run_id,
                task_revision_id=revision_id,
            )
            snapshot = quality.get_review_snapshot(run_id, review_snapshot.snapshot_id)
            reviews = quality.list_review_results(
                run_id,
                task_revision_id=revision_id,
            )
            work.rollback()

        assert stage is not None
        assert stage["stage"] == "reviewing"
        assert stage["attempt"] == 2
        assert stage["task_revision_id"] == revision_id
        assert stage["workspace_state_id"] == state.state_id
        assert persisted_state == state
        assert [item.result_id for item in validations] == [validation.result_id]
        assert snapshot == review_snapshot
        assert [item.review_result_id for item in reviews] == [review.review_result_id]
    finally:
        database.close()


def test_quality_queries_do_not_cross_task_revision_boundaries() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"quality-revision-{uuid.uuid4().hex}"
        old_revision = "revision-old"
        new_revision = "revision-new"
        with unit_of_work(database) as work:
            PostgresAgentRunRepository(work.connection, context).create_run(
                AgentRunSpec(
                    run_id=run_id,
                    task="Implement revised behavior",
                    profile="coding",
                    model=ModelRef(provider_id="test", model_id="test-model"),
                    quality_policy="strict",
                )
            )
            quality = PostgresCodingQualityRepository(work.connection, context)
            for revision_id, suffix in ((old_revision, "old"), (new_revision, "new")):
                state = WorkspaceState(
                    state_id=f"state-{suffix}",
                    run_id=run_id,
                    task_revision_id=revision_id,
                    base_commit_sha="a" * 40,
                    tracked_diff_sha256=("b" if suffix == "old" else "c") * 64,
                    untracked_file_manifest_sha256="d" * 64,
                    modified_paths=[f"src/{suffix}.py"],
                )
                quality.add_workspace_state(state)
                quality.add_validation_result(
                    ValidationResult(
                        run_id=run_id,
                        validation_id="final-state-tests",
                        kind="test",
                        task_revision_id=revision_id,
                        workspace_state_id=state.state_id,
                        command=f"python -m pytest tests/test_{suffix}.py -q",
                        success=True,
                        output_digest=("e" if suffix == "old" else "f") * 64,
                    )
                )
            work.commit()

        with unit_of_work(database) as work:
            quality = PostgresCodingQualityRepository(work.connection, context)
            old = quality.list_validation_results(run_id, task_revision_id=old_revision)
            new = quality.list_validation_results(run_id, task_revision_id=new_revision)
            work.rollback()
        assert [item.workspace_state_id for item in old] == ["state-old"]
        assert [item.workspace_state_id for item in new] == ["state-new"]
    finally:
        database.close()
