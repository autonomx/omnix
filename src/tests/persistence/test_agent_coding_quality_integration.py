from __future__ import annotations

import os
import uuid

import pytest

from app.agent_runtime.coding_quality_repository import PostgresCodingQualityRepository
from app.agent_runtime.contracts import (
    AgentEvent,
    AgentRunSpec,
    ModelRef,
    ReviewFinding,
    ReviewRequirementResult,
    ReviewResult,
    ReviewSnapshot,
    SelfReviewResult,
    ValidationResult,
    WorkspaceState,
)
from app.agent_runtime.quality_recovery import (
    orphaned_quality_review_run_ids,
    reconcile_orphaned_quality_reviews,
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
            covers_requirement_ids=["R1"],
        )
        self_review = SelfReviewResult(run_id=run_id, task_revision_id=revision_id, workspace_state_id=state.state_id, verdict="approve", requirements=[ReviewRequirementResult(requirement_id="R1", status="satisfied", evidence="Exact state checked")])
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
            requirements=[
                ReviewRequirementResult(
                    requirement_id="R1",
                    status="satisfied",
                    evidence="Focused regression demonstrates the requested behavior.",
                )
            ],
            findings=[
                ReviewFinding(
                    severity="low",
                    category="maintainability",
                    file="src/app/example.py",
                    location="example",
                    problem="Minor cleanup remains optional.",
                    recommended_fix="Consider simplifying the helper later.",
                )
            ],
            residual_risks=["A non-blocking compatibility edge remains untested."],
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
            quality.add_self_review_result(self_review)
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
            self_reviews = quality.list_self_review_results(run_id)
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
        assert validations == [validation]
        assert validations[0].covers_requirement_ids == ["R1"]
        assert self_reviews == [self_review]
        assert snapshot == review_snapshot
        assert reviews == [review]
        assert isinstance(reviews[0].requirements[0], ReviewRequirementResult)
        assert isinstance(reviews[0].findings[0], ReviewFinding)
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


def test_orphaned_terminal_reviewer_queues_durable_repair_for_generic_recovery() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"quality-parent-{uuid.uuid4().hex}"
        child_id = f"quality-reviewer-{uuid.uuid4().hex}"

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            parent = repository.create_run(
                AgentRunSpec(
                    run_id=run_id,
                    task="Fix the behavior and add a regression test",
                    objective="Fix the behavior and add a regression test",
                    profile="coding",
                    model=ModelRef(provider_id="test", model_id="test-model"),
                    expected_artifacts=["diff"],
                    quality_policy="strict",
                )
            )
            revision = repository.latest_task_revision(run_id)
            assert revision is not None
            state = WorkspaceState(
                state_id=f"state-{uuid.uuid4().hex}",
                run_id=run_id,
                task_revision_id=revision.revision_id,
                base_commit_sha="a" * 40,
                tracked_diff_sha256="b" * 64,
                untracked_file_manifest_sha256="c" * 64,
                modified_paths=["src/app/example.py"],
            )
            review_snapshot = ReviewSnapshot(
                run_id=run_id,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
                base_commit_sha=state.base_commit_sha,
                patch_checksum=state.state_id,
                workspace_root="/tmp/immutable-review",
            )
            quality = PostgresCodingQualityRepository(work.connection, context)
            quality.add_workspace_state(state)
            quality.add_review_snapshot(review_snapshot)
            quality.set_stage(
                run_id,
                stage="reviewing",
                attempt=1,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
            )
            repository.update_state(
                run_id,
                expected_revision=parent.revision,
                status="waiting_for_children",
                worker_id="dead-quality-worker",
            )
            child = repository.create_run(
                AgentRunSpec(
                    run_id=child_id,
                    parent_run_id=run_id,
                    task=f"REVIEW_SNAPSHOT_ID={review_snapshot.snapshot_id}\nReview immutable snapshot",
                    objective="Review immutable snapshot",
                    profile="coding-reviewer",
                    model=ModelRef(provider_id="test", model_id="review-model"),
                    quality_policy="off",
                    approval_policy="disabled",
                )
            )
            repository.update_state(
                child_id,
                expected_revision=child.revision,
                status="completed",
                worker_id="dead-quality-worker",
            )
            work.commit()

        class _RecoveryService:
            def __init__(self) -> None:
                self.database = database
                self.context = context
                self.worker_id = "replacement-quality-worker"

            @staticmethod
            def _quality_enabled(spec: AgentRunSpec) -> bool:
                return spec.profile == "coding" and "diff" in spec.expected_artifacts

            @staticmethod
            def _current_revision(repository, parent_run_id):
                return repository.latest_task_revision(parent_run_id)

            @staticmethod
            def _review_snapshot_id_from_child(child_snapshot):
                marker = "REVIEW_SNAPSHOT_ID="
                return child_snapshot.spec.task.split(marker, 1)[1].splitlines()[0]

            @staticmethod
            def _review_result_from_child(repository, child_snapshot, snapshot):
                del repository
                return ReviewResult(
                    run_id=run_id,
                    reviewer_run_id=child_snapshot.run_id,
                    review_snapshot_id=snapshot.snapshot_id,
                    task_revision_id=snapshot.task_revision_id,
                    workspace_state_id=snapshot.workspace_state_id,
                    verdict="changes_required",
                    findings=[
                        ReviewFinding(
                            severity="high",
                            category="correctness",
                            problem="Recovered reviewer found a correctness defect.",
                            recommended_fix="Repair the defect and revalidate.",
                        )
                    ],
                )

            @staticmethod
            def _set_quality_stage(
                repository,
                *,
                run_id,
                stage,
                attempt,
                task_revision_id,
                workspace_state_id=None,
                reason=None,
            ):
                quality_repository = PostgresCodingQualityRepository(
                    repository.connection,
                    context,
                )
                quality_repository.set_stage(
                    run_id,
                    stage=stage,
                    attempt=attempt,
                    task_revision_id=task_revision_id,
                    workspace_state_id=workspace_state_id,
                )
                repository.append_event(
                    AgentEvent(
                        run_id=run_id,
                        event_type="quality.stage",
                        payload={
                            "stage": stage,
                            "attempt": attempt,
                            "task_revision_id": task_revision_id,
                            "workspace_state_id": workspace_state_id,
                            "reason": reason,
                        },
                    )
                )

            @staticmethod
            def _launch_reviewer_children(*_args, **_kwargs):
                raise AssertionError("terminal reviewer should be consumed, not relaunched")

        service = _RecoveryService()
        with unit_of_work(database) as work:
            candidates = orphaned_quality_review_run_ids(
                work.connection,
                context.workspace_id,
            )
            work.rollback()
        assert run_id in candidates

        assert reconcile_orphaned_quality_reviews(service) == [run_id]

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            recovered = repository.get_run(run_id)
            pending = repository.list_pending_commands(run_id)
            quality = PostgresCodingQualityRepository(work.connection, context)
            stage = quality.get_stage(run_id)
            reviews = quality.list_review_results(
                run_id,
                task_revision_id=revision.revision_id,
            )
            remaining_candidates = orphaned_quality_review_run_ids(
                work.connection,
                context.workspace_id,
            )
            work.rollback()

        assert recovered is not None
        assert recovered.status == "running"
        assert recovered.desired_state == "running"
        assert stage is not None
        assert stage["stage"] == "repairing"
        assert stage["attempt"] == 2
        assert len(pending) == 1
        assert pending[0].command_type == "resume"
        assert "durably recovered" in str(pending[0].payload.get("message") or "")
        assert [item.verdict for item in reviews] == ["changes_required"]
        assert run_id not in remaining_candidates
    finally:
        database.close()
