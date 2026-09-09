from __future__ import annotations

import json
import os
import uuid

import pytest

from app.agent_runtime.coding_quality_repository import PostgresCodingQualityRepository
from app.agent_runtime.contracts import (
    AgentEvent,
    AgentRunCommand,
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
        browser_validation = ValidationResult(
            run_id=run_id,
            validation_id="browser-validation",
            kind="browser",
            task_revision_id=revision_id,
            workspace_state_id=state.state_id,
            command="omnix_capability browser.assert_text_contains",
            exit_code=0,
            success=True,
            output_digest="e" * 64,
            covers_requirement_ids=["R1"],
        )
        self_review = SelfReviewResult(
            run_id=run_id,
            task_revision_id=revision_id,
            workspace_state_id=state.state_id,
            verdict="approve",
            requirements=[
                ReviewRequirementResult(
                    requirement_id="R1",
                    status="satisfied",
                    evidence="Exact state checked",
                )
            ],
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
            quality.add_validation_result(browser_validation)
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
        assert {item.kind for item in validations} == {"test", "browser"}
        assert validation in validations
        assert browser_validation in validations
        assert all(item.covers_requirement_ids == ["R1"] for item in validations)
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


def test_recovered_substantive_reviewer_verdict_queues_repair_without_runtime_retry() -> None:
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
            repository.append_event(
                AgentEvent(
                    run_id=child_id,
                    event_type="model.message",
                    payload={
                        "phase": "message_end",
                        "text": json.dumps(
                            {
                                "verdict": "changes_required",
                                "requirements": [],
                                "findings": [
                                    {
                                        "severity": "high",
                                        "category": "correctness",
                                        "problem": "Recovered reviewer found a correctness defect.",
                                        "recommended_fix": "Repair the defect and revalidate.",
                                    }
                                ],
                                "missing_tests": [],
                                "residual_risks": [],
                            }
                        ),
                    },
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

            def _request_quality_repair(
                self,
                repository,
                current,
                revision_arg,
                review,
                *,
                failures,
            ):
                assert review is not None
                assert review.verdict == "changes_required"
                assert failures == ["quality_independent_review_not_approved"]
                quality_repository = PostgresCodingQualityRepository(
                    repository.connection,
                    context,
                )
                stage = quality_repository.get_stage(current.run_id) or {"attempt": 1}
                next_attempt = int(stage.get("attempt") or 1) + 1
                self._set_quality_stage(
                    repository,
                    run_id=current.run_id,
                    stage="repairing",
                    attempt=next_attempt,
                    task_revision_id=revision_arg.revision_id,
                    workspace_state_id=review.workspace_state_id,
                    reason="recovered_substantive_review_requires_repair",
                )
                repository.enqueue_command(
                    AgentRunCommand(
                        run_id=current.run_id,
                        command_type="resume",
                        payload={
                            "message": "Repair the recovered substantive reviewer finding.",
                            "quality_stage": "repairing",
                            "quality_attempt": next_attempt,
                            "task_revision_id": revision_arg.revision_id,
                            "workspace_state_id": review.workspace_state_id,
                        },
                        idempotency_key=(
                            f"test-recovered-review-repair:{current.run_id}:"
                            f"{revision_arg.revision_id}:{next_attempt}"
                        ),
                    )
                )
                latest = repository.get_run(current.run_id) or current
                repository.update_state(
                    current.run_id,
                    expected_revision=latest.revision,
                    status="running",
                    desired_state="running",
                    worker_id=self.worker_id,
                    last_error=None,
                )
                return None

            @staticmethod
            def _quality_fail(*_args, **_kwargs):
                raise AssertionError("valid substantive reviewer verdict must not fail review runtime")

            @staticmethod
            def _finalize_acceptance(*_args, **_kwargs):
                raise AssertionError("changes_required must not enter acceptance")

            @staticmethod
            def _launch_reviewer_children(*_args, **_kwargs):
                raise AssertionError("valid substantive reviewer verdict must not be relaunched")

            @staticmethod
            def _dispatch_pending_quality_commands(*_args, **_kwargs):
                # The integration assertion inspects the durable outbox directly.
                return None

            @staticmethod
            def _close_terminal_runtime(*_args, **_kwargs):
                return None

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
            attempts = quality.list_review_attempts(
                run_id,
                review_snapshot_id=review_snapshot.snapshot_id,
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
        assert [item.verdict for item in reviews] == ["changes_required"]
        assert len(attempts) == 1
        assert attempts[0].status == "completed"
        assert attempts[0].failure_class is None
        assert run_id not in remaining_candidates
    finally:
        database.close()
