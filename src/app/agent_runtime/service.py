"""Quality-aware orchestration facade over the stable generalized Agent service core.

The Phase 1-19 durable orchestration remains in service_core. This layer adds the
coding quality state machine: TaskRevision engineering contracts, exact workspace
identity, mandatory self-review, fresh validation, immutable independent review,
and one repair/revalidate/re-review convergence loop. Pi can request completion;
Omnix remains the only completion authority.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import os
from pathlib import Path
import re
import tempfile

from app.persistence.unit_of_work import unit_of_work

from .acceptance import evaluate_acceptance
from .coding_quality import (
    capture_workspace_state,
    compile_task_engineering_contract,
    materialize_review_workspace,
    missing_final_validations,
    parse_review_result,
    quality_attempt_limit,
    quality_failure_reasons,
    relevant_file_candidates,
    repair_prompt,
    required_review_count,
    review_is_acceptable,
    review_prompt,
    self_review_prompt,
    validation_kind_for_command,
    validation_prompt,
    validation_result_from_tool_event,
)
from .coding_quality_repository import PostgresCodingQualityRepository
from .contracts import (
    AgentEvent,
    AgentRunCommand,
    AgentRunSnapshot,
    AgentRunSpec,
    ReviewFinding,
    ReviewResult,
    ReviewSnapshot,
    TaskRevision,
    WorkspaceSpec,
)
from .evidence import evaluate_evidence_set
from .model_fidelity import resolve_run_model_fidelity
from .repository import PostgresAgentRunRepository
from .repository_guidance import compile_repository_guidance
from .semantic_task_parser import default_semantic_task_parser
from .workspace import WorkspaceAuthority
from . import service_core as _service_core
from .service_core import (
    AgentRunService as _CoreAgentRunService,
    _acceptance_failures_retryable,
    _acceptance_retry_count,
)
from .subagents import (
    ChildRunRequest,
    default_reviewer_limits,
    derive_child_spec,
    reserve_child_budget,
)
from .task_revision_quality import (
    hydrate_task_revision,
    hydrate_task_revisions,
    persist_task_revision_contract,
)


_REVIEW_MARKER = re.compile(r"REVIEW_SNAPSHOT_ID=([a-f0-9]+)")
_TERMINAL = {"completed", "failed", "cancelled"}
_BLOCKED_SETTLE = {
    "waiting_for_approval",
    "waiting_for_children",
    "pause_requested",
    "paused",
    "cancel_requested",
    "cancelled",
}
_READ_REVIEW_CAPABILITIES = [
    "workspace.read",
    "workspace.list",
    "workspace.search",
    "workspace.git_status",
    "workspace.git_diff",
]


def _sync_core_compat() -> None:
    """Keep Phase 1-19 patch/test seams anchored at the public service module.

    Before the quality facade existed, tests and local integrations patched
    ``app.agent_runtime.service.unit_of_work``, repository/workspace authority,
    and the semantic parser directly. The implementation now lives in
    ``service_core``; mirror the public facade's current bindings before
    executing inherited code so the split is behaviorally transparent rather
    than a compatibility break.
    """

    _service_core.unit_of_work = unit_of_work
    _service_core.PostgresAgentRunRepository = PostgresAgentRunRepository
    _service_core.WorkspaceAuthority = WorkspaceAuthority
    _service_core.default_semantic_task_parser = default_semantic_task_parser


class AgentRunService(_CoreAgentRunService):
    """Durable generalized Agent service with coding completion quality gates."""

    def __getattribute__(self, name: str):
        # Synchronize on every public/inherited method lookup. This also covers
        # tests that construct the service with object.__new__ and therefore do
        # not run __init__ before exercising a recovery helper.
        if name not in {"__class__", "__dict__", "__getattribute__"}:
            _sync_core_compat()
        return super().__getattribute__(name)

    @staticmethod
    def _quality_enabled(spec: AgentRunSpec) -> bool:
        return (
            spec.profile == "coding"
            and "diff" in spec.expected_artifacts
            and spec.quality_policy != "off"
        )

    def start_with_context(
        self,
        spec: AgentRunSpec,
        *,
        reference_context: str = "",
        reference_images: list[dict[str, str]] | None = None,
    ) -> AgentRunSnapshot:
        # Resolve provider/model/reasoning before the durable RunSpec is written,
        # so observability and recovery see the exact configuration Pi receives.
        resolved = resolve_run_model_fidelity(spec)
        return super().start_with_context(
            resolved,
            reference_context=reference_context,
            reference_images=reference_images,
        )

    def start_child(self, parent_run_id: str, request) -> AgentRunSnapshot:
        """Start a narrowed child while preserving the Phase 1-19 lock contract.

        Keep this implementation on the public service facade rather than only
        in service_core: the lock-before-reservation ordering is part of the
        repository's audited concurrency contract and existing tooling inspects
        this public module directly.
        """

        self._ensure_supervisor()
        initial_parent = self.get(parent_run_id)
        if initial_parent is None:
            raise KeyError(parent_run_id)
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            locked = work.connection.execute(
                """
                SELECT run_id
                  FROM omnix_agent_runs
                 WHERE workspace_id = %s AND run_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, parent_run_id),
            ).fetchone()
            if locked is None:
                raise KeyError(parent_run_id)
            parent = repository.get_run(parent_run_id)
            if parent is None:
                raise KeyError(parent_run_id)
            if parent.status in _TERMINAL:
                raise ValueError("cannot start child from terminal parent")
            child_spec = derive_child_spec(parent, request)
            self._validate_run_spec_authority(child_spec)
            self._validate_evidence_authority(child_spec)
            existing = repository.list_children(parent_run_id)
            parent_usage = repository.get_usage(parent_run_id)
            reserve_child_budget(
                parent,
                existing,
                child_spec,
                parent_usage=parent_usage,
            )
            issued = self._prepare_workspace(
                self._bind_github_repository_authority(child_spec)
            )
            snapshot = self._persist_starting_run(repository, issued)
            work.commit()
        return self._launch_runtime(issued, snapshot)

    def _persist_starting_run(
        self,
        repository: PostgresAgentRunRepository,
        issued: AgentRunSpec,
    ) -> AgentRunSnapshot:
        snapshot = super()._persist_starting_run(repository, issued)
        revision = repository.latest_task_revision(issued.run_id)
        if revision is not None:
            mutating = "diff" in revision.expected_artifacts
            requirements, constraints, validation_plan = compile_task_engineering_contract(
                revision.effective_objective,
                revision.effective_success_criteria,
                profile=issued.profile,
                mutating=mutating,
            )
            revision = revision.model_copy(
                update={
                    "requirements": requirements,
                    "constraints": constraints,
                    "validation_plan": validation_plan,
                }
            )
            persist_task_revision_contract(repository.connection, self.context, revision)
            if self._quality_enabled(issued):
                quality = PostgresCodingQualityRepository(repository.connection, self.context)
                quality.set_stage(
                    issued.run_id,
                    stage="implementing",
                    attempt=1,
                    task_revision_id=revision.revision_id,
                )
                repository.append_event(
                    AgentEvent(
                        run_id=issued.run_id,
                        event_type="quality.stage",
                        payload={
                            "stage": "implementing",
                            "attempt": 1,
                            "task_revision_id": revision.revision_id,
                        },
                    )
                )
        return snapshot

    def get(self, run_id: str) -> AgentRunSnapshot | None:
        snapshot = super().get(run_id)
        if snapshot is None:
            return None
        try:
            with unit_of_work(self.database) as work:
                quality = PostgresCodingQualityRepository(work.connection, self.context)
                stage = quality.get_stage(run_id)
                work.rollback()
        except Exception:
            return snapshot
        if stage is None:
            return snapshot
        return snapshot.model_copy(
            update={
                "quality_stage": stage.get("stage"),
                "quality_attempt": int(stage.get("attempt") or 0),
                "workspace_state_id": stage.get("workspace_state_id"),
            }
        )

    def task_revisions(self, run_id: str) -> list[TaskRevision]:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            rows = hydrate_task_revisions(
                work.connection,
                self.context,
                repository.list_task_revisions(run_id),
            )
            work.rollback()
        return rows

    def quality_state(self, run_id: str) -> dict[str, object] | None:
        with unit_of_work(self.database) as work:
            if PostgresAgentRunRepository(work.connection, self.context).get_run(run_id) is None:
                work.rollback()
                raise KeyError(run_id)
            row = PostgresCodingQualityRepository(work.connection, self.context).get_stage(run_id)
            work.rollback()
        return row

    def validation_results(self, run_id: str):
        with unit_of_work(self.database) as work:
            rows = PostgresCodingQualityRepository(work.connection, self.context).list_validation_results(run_id)
            work.rollback()
        return rows

    def review_results(self, run_id: str):
        with unit_of_work(self.database) as work:
            rows = PostgresCodingQualityRepository(work.connection, self.context).list_review_results(run_id)
            work.rollback()
        return rows

    def command_with_context(
        self,
        command: AgentRunCommand,
        *,
        reference_context: str = "",
        reference_images: list[dict[str, str]] | None = None,
        turn_plan=None,
    ) -> AgentRunSnapshot:
        result = super().command_with_context(
            command,
            reference_context=reference_context,
            reference_images=reference_images,
            turn_plan=turn_plan,
        )
        if command.command_type != "steer" or result.run_id != command.run_id:
            return result

        stale_reviewers: list[str] = []
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            current = repository.get_run(command.run_id)
            revision = repository.latest_task_revision(command.run_id)
            if current is not None and revision is not None:
                requirements, constraints, validation_plan = compile_task_engineering_contract(
                    revision.effective_objective,
                    revision.effective_success_criteria,
                    profile=current.spec.profile,
                    mutating="diff" in revision.expected_artifacts,
                )
                revision = revision.model_copy(
                    update={
                        "requirements": requirements,
                        "constraints": constraints,
                        "validation_plan": validation_plan,
                    }
                )
                persist_task_revision_contract(work.connection, self.context, revision)
                if self._quality_enabled(current.spec) and current.status not in _TERMINAL:
                    quality = PostgresCodingQualityRepository(work.connection, self.context)
                    quality.set_stage(
                        current.run_id,
                        stage="implementing",
                        attempt=1,
                        task_revision_id=revision.revision_id,
                    )
                    repository.append_event(
                        AgentEvent(
                            run_id=current.run_id,
                            event_type="quality.stage",
                            payload={
                                "stage": "implementing",
                                "attempt": 1,
                                "task_revision_id": revision.revision_id,
                                "reason": "task_revision_changed",
                            },
                        )
                    )
                    stale_reviewers = [
                        child.run_id
                        for child in repository.list_children(current.run_id)
                        if child.spec.profile == "coding-reviewer" and child.status not in _TERMINAL
                    ]
            work.commit()

        for child_id in stale_reviewers:
            try:
                self.command(
                    AgentRunCommand(
                        run_id=child_id,
                        command_type="cancel",
                        payload={"reason": "parent_task_revision_changed"},
                        idempotency_key=f"quality-stale-reviewer:{command.run_id}:{child_id}",
                    )
                )
            except Exception:
                # Stale review evidence is revision-bound and cannot pass even
                # if best-effort cancellation loses a race with completion.
                pass
        return self.get(result.run_id) or result

    def _current_revision(
        self,
        repository: PostgresAgentRunRepository,
        run_id: str,
    ) -> TaskRevision | None:
        revision = repository.latest_task_revision(run_id)
        if revision is None:
            return None
        revision = hydrate_task_revision(repository.connection, self.context, revision)
        if revision.requirements or revision.validation_plan:
            return revision
        current = repository.get_run(run_id)
        if current is None:
            return revision
        requirements, constraints, validation_plan = compile_task_engineering_contract(
            revision.effective_objective,
            revision.effective_success_criteria,
            profile=current.spec.profile,
            mutating="diff" in revision.expected_artifacts,
        )
        revision = revision.model_copy(
            update={
                "requirements": requirements,
                "constraints": constraints,
                "validation_plan": validation_plan,
            }
        )
        persist_task_revision_contract(repository.connection, self.context, revision)
        return revision

    def _set_quality_stage(
        self,
        repository: PostgresAgentRunRepository,
        *,
        run_id: str,
        stage: str,
        attempt: int,
        task_revision_id: str | None,
        workspace_state_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        quality = PostgresCodingQualityRepository(repository.connection, self.context)
        quality.set_stage(
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
                    **({"reason": reason} if reason else {}),
                },
            )
        )

    def _record_workspace_tool_result(self, event: AgentEvent) -> None:
        call_id = str(event.payload.get("tool_call_id") or "")
        if not call_id:
            return
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            current = repository.get_run(event.run_id)
            if current is None or current.status in _TERMINAL or not self._quality_enabled(current.spec):
                work.rollback()
                return
            events = repository.list_events(event.run_id, after_sequence=0, limit=5000)
            started = next(
                (
                    item
                    for item in reversed(events)
                    if item.event_type == "tool.started"
                    and str(item.payload.get("tool_call_id") or "") == call_id
                ),
                None,
            )
            tool = str(event.payload.get("tool") or (started.payload.get("tool") if started else "") or "")
            args = started.payload.get("args") if started and isinstance(started.payload.get("args"), dict) else {}
            command = str(args.get("command") or "")
            mutating_or_validation = tool in {"edit", "write", "bash", "powershell"} or validation_kind_for_command(command) is not None
            if not mutating_or_validation:
                work.rollback()
                return
            revision = self._current_revision(repository, event.run_id)
            active_revision_id = revision.revision_id if revision is not None else None
            event_revision_id = event.payload.get("task_revision_id")
            bound_revision_id = str(event_revision_id) if event_revision_id else active_revision_id
            state = capture_workspace_state(current.spec, task_revision_id=bound_revision_id)
            if state is None:
                work.rollback()
                return
            quality = PostgresCodingQualityRepository(work.connection, self.context)
            quality.add_workspace_state(state)
            augmented = event.model_copy(
                update={
                    "payload": {
                        **event.payload,
                        "args": args,
                        "command": command,
                    }
                }
            )
            validation = validation_result_from_tool_event(
                augmented,
                run_id=event.run_id,
                task_revision_id=bound_revision_id,
                workspace_state_id=state.state_id,
                revision=revision if bound_revision_id == active_revision_id else None,
            )
            if validation is not None:
                quality.add_validation_result(validation)
                repository.append_event(
                    AgentEvent(
                        run_id=event.run_id,
                        event_type="quality.validation_recorded",
                        payload={
                            "result_id": validation.result_id,
                            "validation_id": validation.validation_id,
                            "kind": validation.kind,
                            "success": validation.success,
                            "task_revision_id": validation.task_revision_id,
                            "workspace_state_id": validation.workspace_state_id,
                            "command": validation.command,
                        },
                    )
                )
            work.commit()

    def _persist_runtime_event(self, event: AgentEvent) -> None:
        if event.event_type not in {"run.settled", "run.completed"}:
            super()._persist_runtime_event(event)
            if event.event_type == "tool.completed":
                self._record_workspace_tool_result(event)
            return

        with unit_of_work(self.database) as probe:
            current = PostgresAgentRunRepository(probe.connection, self.context).get_run(event.run_id)
            probe.rollback()
        if current is None or not self._quality_enabled(current.spec):
            super()._persist_runtime_event(event)
            return

        post_action: tuple | None = None
        with self._lock:
            with unit_of_work(self.database) as work:
                repository = PostgresAgentRunRepository(work.connection, self.context)
                current = repository.get_run(event.run_id)
                if current is None:
                    work.rollback()
                    return
                repository.append_event(event)
                if current.status in _TERMINAL or current.status in _BLOCKED_SETTLE:
                    work.commit()
                    return
                post_action = self._advance_quality_on_settle(repository, current)
                work.commit()
        self._execute_quality_action(post_action)

    def _advance_quality_on_settle(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
    ) -> tuple | None:
        revision = self._current_revision(repository, current.run_id)
        if revision is None:
            repository.update_state(
                current.run_id,
                expected_revision=current.revision,
                status="failed",
                last_error="quality_task_revision_unavailable",
            )
            return None
        quality = PostgresCodingQualityRepository(repository.connection, self.context)
        stage_state = quality.get_stage(current.run_id) or {
            "stage": "implementing",
            "attempt": 1,
            "task_revision_id": revision.revision_id,
            "workspace_state_id": None,
        }
        stage = str(stage_state.get("stage") or "implementing")
        attempt = max(1, int(stage_state.get("attempt") or 1))

        if stage in {"inspect", "planning", "implementing", "repairing"}:
            self._set_quality_stage(
                repository,
                run_id=current.run_id,
                stage="self_review",
                attempt=attempt,
                task_revision_id=revision.revision_id,
                reason="implementation_candidate_settled",
            )
            return (
                "resume",
                current.run_id,
                self_review_prompt(revision, attempt=attempt),
                f"quality-self-review:{current.run_id}:{revision.revision_id}:{attempt}",
            )

        state = capture_workspace_state(current.spec, task_revision_id=revision.revision_id)
        if state is None:
            return self._quality_fail(repository, current, "quality_workspace_state_unavailable")
        quality.add_workspace_state(state)

        if stage == "self_review":
            repository.append_event(
                AgentEvent(
                    run_id=current.run_id,
                    event_type="quality.self_review_completed",
                    payload={
                        "attempt": attempt,
                        "task_revision_id": revision.revision_id,
                        "workspace_state_id": state.state_id,
                    },
                )
            )
            self._set_quality_stage(
                repository,
                run_id=current.run_id,
                stage="validating",
                attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
            )

        events = repository.list_events(current.run_id, after_sequence=0, limit=5000)
        self_review_fresh = any(
            item.event_type == "quality.self_review_completed"
            and item.payload.get("task_revision_id") == revision.revision_id
            and item.payload.get("workspace_state_id") == state.state_id
            for item in events
        )
        if not self_review_fresh:
            self._set_quality_stage(
                repository,
                run_id=current.run_id,
                stage="self_review",
                attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
                reason="workspace_changed_after_self_review",
            )
            return (
                "resume",
                current.run_id,
                self_review_prompt(revision, attempt=attempt),
                f"quality-self-review-refresh:{current.run_id}:{state.state_id}:{attempt}",
            )

        validations = quality.list_validation_results(
            current.run_id,
            task_revision_id=revision.revision_id,
        )
        missing = missing_final_validations(
            revision,
            validations,
            workspace_state_id=state.state_id,
        )
        if missing:
            self._set_quality_stage(
                repository,
                run_id=current.run_id,
                stage="validating",
                attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
                reason="final_state_validation_missing_or_stale",
            )
            return (
                "resume",
                current.run_id,
                validation_prompt(revision, missing),
                f"quality-validation:{current.run_id}:{state.state_id}:{attempt}",
            )

        review_count = required_review_count(current.spec, state)
        if review_count <= 0:
            self._set_quality_stage(
                repository,
                run_id=current.run_id,
                stage="acceptance",
                attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
            )
            self._finalize_acceptance(repository, current)
            return None

        self._capture_diff(repository, current.spec, task_revision_id=revision.revision_id)
        artifacts = repository.list_artifacts(current.run_id)
        diff_artifact = next(
            (
                artifact
                for artifact in reversed(artifacts)
                if artifact.kind == "diff"
                and artifact.metadata.get("task_revision_id") == revision.revision_id
            ),
            None,
        )
        review_root = os.environ.get(
            "OMNIX_AGENT_REVIEW_ROOT",
            str(Path(tempfile.gettempdir()) / "omnix-agent-review-snapshots"),
        )
        review_workspace = materialize_review_workspace(
            current.spec,
            state,
            review_root=review_root,
        )
        _, guidance_digest = compile_repository_guidance(
            current.spec.workspace,
            objective=revision.effective_objective,
            relevant_paths=state.modified_paths,
        )
        current_validation_ids = [
            item.result_id
            for item in validations
            if item.workspace_state_id == state.state_id and item.success
        ]
        review_snapshot = ReviewSnapshot(
            run_id=current.run_id,
            task_revision_id=revision.revision_id,
            workspace_state_id=state.state_id,
            base_commit_sha=state.base_commit_sha,
            patch_checksum=state.state_id,
            patch_storage_ref=diff_artifact.storage_ref if diff_artifact else None,
            workspace_root=review_workspace.root,
            relevant_files=relevant_file_candidates(revision, state),
            validation_result_ids=current_validation_ids,
            repository_guidance_digest=guidance_digest,
        )
        quality.add_review_snapshot(review_snapshot)
        self._set_quality_stage(
            repository,
            run_id=current.run_id,
            stage="reviewing",
            attempt=attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=state.state_id,
        )
        latest = repository.get_run(current.run_id) or current
        repository.update_state(
            current.run_id,
            expected_revision=latest.revision,
            status="waiting_for_children",
            worker_id=self.worker_id,
        )
        repository.append_event(
            AgentEvent(
                run_id=current.run_id,
                event_type="quality.review_started",
                payload={
                    "attempt": attempt,
                    "review_snapshot_id": review_snapshot.snapshot_id,
                    "task_revision_id": revision.revision_id,
                    "workspace_state_id": state.state_id,
                    "reviewer_count": review_count,
                },
            )
        )
        return ("launch_reviews", current.run_id, review_snapshot.snapshot_id, review_count)

    def _execute_quality_action(self, action: tuple | None) -> None:
        if not action:
            return
        if action[0] == "resume":
            _, run_id, prompt, key = action
            try:
                self.runtime.command(
                    AgentRunCommand(
                        run_id=run_id,
                        command_type="resume",
                        payload={"message": prompt},
                        idempotency_key=key,
                    )
                )
            except Exception as exc:
                with unit_of_work(self.database) as work:
                    repository = PostgresAgentRunRepository(work.connection, self.context)
                    current = repository.get_run(run_id)
                    if current is not None and current.status not in _TERMINAL:
                        repository.update_state(
                            run_id,
                            expected_revision=current.revision,
                            status="failed",
                            desired_state="cancelled",
                            last_error=f"quality_resume_failed:{type(exc).__name__}:{exc}"[:2000],
                        )
                    work.commit()
            return
        if action[0] == "launch_reviews":
            _, parent_run_id, snapshot_id, count = action
            self._launch_reviewer_children(parent_run_id, snapshot_id, int(count))

    def _launch_reviewer_children(self, parent_run_id: str, snapshot_id: str, count: int) -> None:
        for index in range(max(1, count)):
            launch: tuple[AgentRunSpec, AgentRunSnapshot] | None = None
            with unit_of_work(self.database) as work:
                repository = PostgresAgentRunRepository(work.connection, self.context)
                parent = repository.get_run(parent_run_id)
                if parent is None or parent.status in _TERMINAL:
                    work.rollback()
                    return
                quality = PostgresCodingQualityRepository(work.connection, self.context)
                snapshot = quality.get_review_snapshot(parent_run_id, snapshot_id)
                revision = self._current_revision(repository, parent_run_id)
                if snapshot is None or revision is None:
                    work.rollback()
                    return
                if (
                    snapshot.task_revision_id != revision.revision_id
                    or snapshot.workspace_state_id != (quality.get_stage(parent_run_id) or {}).get("workspace_state_id")
                ):
                    work.rollback()
                    return
                validations = quality.list_validation_results(
                    parent_run_id,
                    task_revision_id=revision.revision_id,
                )
                prompt = (
                    f"REVIEW_SNAPSHOT_ID={snapshot.snapshot_id}\n"
                    + review_prompt(revision, snapshot, validations)
                )
                workspace = WorkspaceSpec(
                    root=snapshot.workspace_root,
                    repository=(parent.spec.workspace.repository if parent.spec.workspace else None)
                    or (parent.spec.workspace.root if parent.spec.workspace else snapshot.workspace_root),
                    base_ref=snapshot.base_commit_sha,
                    worktree=snapshot.workspace_root,
                    isolation_policy="immutable_review_snapshot",
                    allowed_paths=list(parent.spec.workspace.allowed_paths if parent.spec.workspace else ["**"]),
                    forbidden_paths=list(parent.spec.workspace.forbidden_paths if parent.spec.workspace else []),
                )
                per_reviewer_fraction = parent.spec.quality_reserve_fraction / max(1, count)
                request = ChildRunRequest(
                    task=prompt,
                    objective=prompt,
                    profile_id="coding-reviewer",
                    provider_id=parent.spec.model.provider_id,
                    model_id=parent.spec.model.model_id,
                    reasoning_effort=parent.spec.model.reasoning_effort,
                    capabilities=list(_READ_REVIEW_CAPABILITIES),
                    external_capabilities=[],
                    success_criteria=["Return a structured independent review verdict for the immutable snapshot."],
                    limits=default_reviewer_limits(parent.spec.limits, per_reviewer_fraction),
                )
                child_spec = derive_child_spec(parent, request, workspace_override=workspace)
                deterministic_id = hashlib.sha256(
                    f"review:{parent_run_id}:{snapshot_id}:{index}".encode("utf-8")
                ).hexdigest()
                child_spec = child_spec.model_copy(update={"run_id": deterministic_id})
                existing = repository.get_run(deterministic_id)
                if existing is not None:
                    work.rollback()
                    if existing.status in _TERMINAL:
                        continue
                    if self.runtime.get_status(existing.run_id) is None:
                        try:
                            self.runtime.start(existing.spec)
                        except Exception:
                            pass
                    continue
                self._validate_run_spec_authority(child_spec)
                self._validate_evidence_authority(child_spec)
                children = repository.list_children(parent_run_id)
                reserve_child_budget(
                    parent,
                    children,
                    child_spec,
                    parent_usage=repository.get_usage(parent_run_id),
                )
                issued = self._prepare_workspace(self._bind_github_repository_authority(child_spec))
                child_snapshot = self._persist_starting_run(repository, issued)
                launch = (issued, child_snapshot)
                work.commit()
            if launch is not None:
                self._launch_runtime(launch[0], launch[1])

    @staticmethod
    def _review_snapshot_id_from_child(child: AgentRunSnapshot) -> str | None:
        match = _REVIEW_MARKER.search(child.spec.task)
        return match.group(1) if match else None

    def _review_result_from_child(
        self,
        repository: PostgresAgentRunRepository,
        child: AgentRunSnapshot,
        snapshot: ReviewSnapshot,
    ) -> ReviewResult:
        events = repository.list_events(child.run_id, after_sequence=0, limit=5000)
        text = ""
        for event in reversed(events):
            if event.event_type == "model.message":
                candidate = str(event.payload.get("text") or "").strip()
                if candidate:
                    text = candidate
                    break
        if child.status == "completed":
            result = parse_review_result(
                text,
                parent_run_id=child.spec.parent_run_id or snapshot.run_id,
                reviewer_run_id=child.run_id,
                snapshot=snapshot,
            )
        else:
            result = ReviewResult(
                run_id=child.spec.parent_run_id or snapshot.run_id,
                reviewer_run_id=child.run_id,
                review_snapshot_id=snapshot.snapshot_id,
                task_revision_id=snapshot.task_revision_id,
                workspace_state_id=snapshot.workspace_state_id,
                verdict="blocked",
                findings=[
                    ReviewFinding(
                        severity="high",
                        category="review_runtime",
                        problem=f"Independent reviewer ended with status {child.status}.",
                        recommended_fix="Re-run independent review against the same immutable snapshot.",
                    )
                ],
            )
        deterministic_result_id = hashlib.sha256(
            f"review-result:{child.run_id}:{snapshot.snapshot_id}".encode("utf-8")
        ).hexdigest()
        return result.model_copy(update={"review_result_id": deterministic_result_id})

    def _maybe_finalize_parent_in_repository(
        self,
        repository: PostgresAgentRunRepository,
        child_run_id: str,
    ) -> None:
        child = repository.get_run(child_run_id)
        if (
            child is None
            or child.spec.profile != "coding-reviewer"
            or not child.spec.parent_run_id
            or child.status not in _TERMINAL
        ):
            super()._maybe_finalize_parent_in_repository(repository, child_run_id)
            return
        parent = repository.get_run(child.spec.parent_run_id)
        if parent is None or not self._quality_enabled(parent.spec):
            super()._maybe_finalize_parent_in_repository(repository, child_run_id)
            return
        quality = PostgresCodingQualityRepository(repository.connection, self.context)
        stage = quality.get_stage(parent.run_id)
        if parent.status != "waiting_for_children" or stage is None or stage.get("stage") != "reviewing":
            return
        snapshot_id = self._review_snapshot_id_from_child(child)
        if not snapshot_id:
            return
        snapshot = quality.get_review_snapshot(parent.run_id, snapshot_id)
        revision = self._current_revision(repository, parent.run_id)
        if snapshot is None or revision is None:
            return
        if (
            snapshot.task_revision_id != revision.revision_id
            or snapshot.workspace_state_id != stage.get("workspace_state_id")
        ):
            return

        result = self._review_result_from_child(repository, child, snapshot)
        quality.add_review_result(result)
        repository.append_event(
            AgentEvent(
                run_id=parent.run_id,
                event_type="quality.review_completed",
                payload={
                    "reviewer_run_id": child.run_id,
                    "review_snapshot_id": snapshot.snapshot_id,
                    "verdict": result.verdict,
                    "findings": [item.model_dump(mode="json") for item in result.findings],
                    "missing_tests": list(result.missing_tests),
                    "task_revision_id": result.task_revision_id,
                    "workspace_state_id": result.workspace_state_id,
                },
            )
        )

        matching_children = [
            item
            for item in repository.list_children(parent.run_id)
            if item.spec.profile == "coding-reviewer"
            and self._review_snapshot_id_from_child(item) == snapshot.snapshot_id
        ]
        if any(item.status not in _TERMINAL for item in matching_children):
            return

        results = quality.list_review_results(
            parent.run_id,
            task_revision_id=revision.revision_id,
        )
        current_results = [
            item
            for item in results
            if item.workspace_state_id == snapshot.workspace_state_id
            and item.review_snapshot_id == snapshot.snapshot_id
        ]
        required = required_review_count(
            parent.spec,
            quality.get_workspace_state(parent.run_id, snapshot.workspace_state_id),
        )
        approvals = [item for item in current_results if review_is_acceptable(item, revision)]
        if len(approvals) >= required:
            self._set_quality_stage(
                repository,
                run_id=parent.run_id,
                stage="acceptance",
                attempt=int(stage.get("attempt") or 1),
                task_revision_id=revision.revision_id,
                workspace_state_id=snapshot.workspace_state_id,
            )
            latest = repository.get_run(parent.run_id) or parent
            if latest.status == "waiting_for_children":
                latest = repository.update_state(
                    parent.run_id,
                    expected_revision=latest.revision,
                    status="running",
                    worker_id=self.worker_id,
                )
            self._finalize_acceptance(repository, latest)
            return

        latest_review = next(
            (item for item in reversed(current_results) if item.verdict != "approve"),
            current_results[-1] if current_results else None,
        )
        self._request_quality_repair(
            repository,
            parent,
            revision,
            latest_review,
            failures=["quality_independent_review_missing_or_not_approved"],
        )

    def _request_quality_repair(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
        revision: TaskRevision,
        review: ReviewResult | None,
        *,
        failures: list[str],
    ) -> None:
        quality = PostgresCodingQualityRepository(repository.connection, self.context)
        stage = quality.get_stage(current.run_id) or {"attempt": 1, "workspace_state_id": None}
        attempt = max(1, int(stage.get("attempt") or 1))
        if attempt >= quality_attempt_limit():
            latest = repository.get_run(current.run_id) or current
            repository.update_state(
                current.run_id,
                expected_revision=latest.revision,
                status="failed",
                desired_state="cancelled",
                last_error=("quality_failed:" + ",".join(failures))[:2000],
            )
            return
        next_attempt = attempt + 1
        state_id = stage.get("workspace_state_id")
        validations = quality.list_validation_results(
            current.run_id,
            task_revision_id=revision.revision_id,
        )
        missing = missing_final_validations(
            revision,
            validations,
            workspace_state_id=str(state_id or ""),
        ) if state_id else list(revision.validation_plan)
        prompt = repair_prompt(
            revision,
            review,
            missing,
            attempt=next_attempt,
        )
        if failures:
            prompt += "\nOmnix acceptance/quality failures: " + ", ".join(failures)
        self._set_quality_stage(
            repository,
            run_id=current.run_id,
            stage="repairing",
            attempt=next_attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=str(state_id) if state_id else None,
            reason="quality_gate_requires_repair",
        )
        repository.append_event(
            AgentEvent(
                run_id=current.run_id,
                event_type="quality.repair_requested",
                payload={
                    "attempt": next_attempt,
                    "failures": failures,
                    "task_revision_id": revision.revision_id,
                    "workspace_state_id": state_id,
                },
            )
        )
        latest = repository.get_run(current.run_id) or current
        if latest.status != "running":
            latest = repository.update_state(
                current.run_id,
                expected_revision=latest.revision,
                status="running",
                desired_state="running",
                worker_id=self.worker_id,
                last_error=None,
            )
        try:
            self.runtime.command(
                AgentRunCommand(
                    run_id=current.run_id,
                    command_type="resume",
                    payload={"message": prompt},
                    idempotency_key=(
                        f"quality-repair:{current.run_id}:{revision.revision_id}:{next_attempt}:"
                        f"{hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:16]}"
                    ),
                )
            )
        except Exception as exc:
            latest = repository.get_run(current.run_id) or latest
            repository.update_state(
                current.run_id,
                expected_revision=latest.revision,
                status="failed",
                desired_state="cancelled",
                last_error=f"quality_repair_resume_failed:{type(exc).__name__}:{exc}"[:2000],
            )

    def _quality_fail(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
        reason: str,
    ) -> None:
        latest = repository.get_run(current.run_id) or current
        repository.update_state(
            current.run_id,
            expected_revision=latest.revision,
            status="failed",
            desired_state="cancelled",
            last_error=reason[:2000],
        )
        return None

    def _finalize_acceptance(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
    ) -> None:
        if not self._quality_enabled(current.spec):
            super()._finalize_acceptance(repository, current)
            return

        revision = self._current_revision(repository, current.run_id)
        revision_id = revision.revision_id if revision is not None else None
        repository.append_event(
            AgentEvent(
                run_id=current.run_id,
                event_type="acceptance.started",
                payload={"source": "omnix", "task_revision_id": revision_id},
            )
        )
        self._capture_diff(repository, current.spec, task_revision_id=revision_id)
        all_events = repository.list_events(current.run_id, after_sequence=0, limit=5000)
        all_artifacts = repository.list_artifacts(current.run_id)
        all_receipts = repository.list_evidence_receipts(current.run_id)
        events = self._events_for_revision(all_events, revision)
        artifacts = self._artifacts_for_revision(all_artifacts, revision)
        receipts = self._receipts_for_revision(all_receipts, revision)
        effective_policy = revision.evidence_decision.policy if revision is not None else current.spec.evidence_policy
        evidence_set = evaluate_evidence_set(current.run_id, effective_policy, receipts)
        result = evaluate_acceptance(
            current.spec,
            events=events,
            artifacts=artifacts,
            task_revision=revision,
            evidence_set=evidence_set,
        )

        quality = PostgresCodingQualityRepository(repository.connection, self.context)
        state = capture_workspace_state(current.spec, task_revision_id=revision_id)
        if state is not None:
            quality.add_workspace_state(state)
        validations = quality.list_validation_results(current.run_id, task_revision_id=revision_id)
        reviews = quality.list_review_results(current.run_id, task_revision_id=revision_id)
        quality_failures = quality_failure_reasons(
            current,
            revision,
            state,
            validations,
            reviews,
            all_events,
        )

        non_reviewer_children = [
            child for child in repository.list_children(current.run_id)
            if child.spec.profile != "coding-reviewer"
        ]
        children_terminal = all(child.status in _TERMINAL for child in non_reviewer_children)
        child_failed = any(child.status in {"failed", "cancelled"} for child in non_reviewer_children)
        failures = list(result.failures) + list(quality_failures)
        if not children_terminal:
            failures.append("children_not_terminal")
        if child_failed:
            failures.append("child_run_failed")
        passed = result.passed and not failures

        repository.append_event(
            AgentEvent(
                run_id=current.run_id,
                event_type="acceptance.completed",
                payload={
                    **result.model_dump(mode="json"),
                    "passed": passed,
                    "failures": failures,
                    "retrying": False,
                    "task_revision_id": revision_id,
                    "workspace_state_id": state.state_id if state else None,
                    "evidence_set": evidence_set.model_dump(mode="json"),
                    "quality_policy": current.spec.quality_policy,
                },
            )
        )
        latest = repository.get_run(current.run_id) or current
        if passed:
            self._set_quality_stage(
                repository,
                run_id=current.run_id,
                stage="acceptance",
                attempt=max(1, int((quality.get_stage(current.run_id) or {}).get("attempt") or 1)),
                task_revision_id=revision_id,
                workspace_state_id=state.state_id if state else None,
            )
            latest = repository.get_run(current.run_id) or latest
            repository.update_state(
                current.run_id,
                expected_revision=latest.revision,
                status="completed",
                worker_id=self.worker_id,
                last_error=None,
            )
            return

        repairable_acceptance = _acceptance_failures_retryable(list(result.failures)) if result.failures else True
        fail_closed = any(
            failure in {
                "modified_paths_outside_scope",
                "preexisting_dirty_paths_modified",
                "evidence_requirements_unsatisfied",
                "user_visible_attribution_unavailable",
                "child_run_failed",
            }
            for failure in failures
        )
        if revision is not None and repairable_acceptance and not fail_closed:
            latest_review = next(
                (
                    review
                    for review in reversed(reviews)
                    if state is not None and review.workspace_state_id == state.state_id
                ),
                None,
            )
            self._request_quality_repair(
                repository,
                latest,
                revision,
                latest_review,
                failures=failures,
            )
            return

        latest = repository.get_run(current.run_id) or latest
        repository.update_state(
            current.run_id,
            expected_revision=latest.revision,
            status="failed",
            desired_state="cancelled",
            worker_id=self.worker_id,
            last_error=("acceptance_failed:" + ",".join(failures))[:2000],
        )


@lru_cache(maxsize=1)
def default_agent_run_service() -> AgentRunService:
    return AgentRunService()
