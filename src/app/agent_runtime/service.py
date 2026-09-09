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
import tempfile

from app.persistence.unit_of_work import unit_of_work

from .acceptance import evaluate_acceptance
from .coding_quality import (
    capture_workspace_state,
    compile_task_engineering_contract,
    materialize_review_workspace,
    missing_final_validations,
    parse_review_result,
    parse_self_review_result,
    quality_attempt_limit,
    quality_failure_reasons,
    relevant_file_candidates,
    repair_prompt,
    required_review_count,
    review_is_acceptable,
    review_payload_from_text,
    self_review_is_acceptable,
    self_review_prompt,
    validation_kind_for_capability,
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
    ReviewResult,
    ReviewSnapshot,
    SelfReviewResult,
    TaskRevision,
)
from .debug_logging import log_agent_activity
from .evidence import evaluate_evidence_set
from .model_fidelity import resolve_run_model_fidelity
from .planning_acceptance import evaluate_planning_acceptance
from .repository import PostgresAgentRunRepository
from .repository_guidance import compile_repository_guidance
from .quality_recovery import reconcile_orphaned_quality_reviews
from .resource_grants import PostgresResourceGrantRepository
from .review_orchestration import (
    finalize_reviewer_child_in_repository,
    launch_reviewer_children,
    review_snapshot_id_from_child,
)
from .review_runtime import latest_reviewer_text, review_payload_is_protocol_valid
from .semantic_task_parser import default_semantic_task_parser
from .workspace import WorkspaceAuthority
from . import service_core as _service_core
from .service_core import (
    AgentRunService as _CoreAgentRunService,
    _acceptance_failures_retryable,
    _acceptance_retry_count as _acceptance_retry_count,
)
from .subagents import ChildRunRequest, derive_child_spec
from .task_revision_quality import (
    hydrate_task_revision,
    hydrate_task_revisions,
    persist_task_revision_contract,
)


_TERMINAL = {"completed", "failed", "cancelled"}
_BLOCKED_SETTLE = {
    "waiting_for_approval",
    "waiting_for_input",
    "waiting_for_children",
    "pause_requested",
    "paused",
    "cancel_requested",
    "cancelled",
}


def _is_structured_self_review_message(event: AgentEvent) -> bool:
    """Recognize the terminal payload of the mandatory self-review turn.

    Pi emits ``run.settled`` for the initial implementation turn, but some
    RPC sessions only emit ``message_end`` after a quality-stage resume. The
    self-review prompt requires one JSON object and no tools, so this is a
    safe, deterministic fallback signal for advancing that stage.
    """

    if event.event_type != "model.message" or event.payload.get("phase") not in {"message_end", "turn_end"}:
        return False
    text = str(event.payload.get("text") or "").strip()
    return bool(review_payload_from_text(text))


def _is_terminal_self_review_message(event: AgentEvent) -> bool:
    """Return true for a visible terminal assistant response.

    This is intentionally broader than the structured-verdict predicate so
    observability can still recognize malformed self-review output. Malformed
    output does not itself settle a self-review turn; Omnix waits for the Pi
    settle boundary (or the stalled-run supervisor) before retrying the
    transport protocol. That prevents a trailing ``run.settled`` from consuming
    a second retry after a retry prompt has already been dispatched.
    """

    return (
        event.event_type == "model.message"
        and event.payload.get("phase") in {"message_end", "turn_end"}
        and bool(str(event.payload.get("text") or "").strip())
    )


def _terminal_message_settles_quality_stage(event: AgentEvent, stage: str) -> bool:
    """Treat only a structured verdict in the explicit self-review stage as a boundary.

    Normal Pi sessions emit ``run.settled`` after terminal assistant text. If
    malformed prose were allowed to settle the self-review stage immediately,
    the retry prompt could be sent before that trailing settle event and the
    same turn could burn two protocol retries. A structured verdict may advance
    early only after Omnix has durably entered ``self_review``. Structured JSON
    emitted by implementation or repair turns is never self-review evidence;
    those stages advance only at the Pi settle boundary.
    """

    return stage == "self_review" and _is_structured_self_review_message(event)


def _self_review_payload_is_protocol_valid(text: str, revision: TaskRevision) -> bool:
    """Validate the transport/schema contract separately from review quality.

    A missing or malformed payload is a protocol failure, not evidence that the
    implementation itself failed review. Keep that distinction explicit so
    protocol retries do not consume the bounded repair attempts.
    """

    payload = review_payload_from_text(text)
    if not payload:
        return False
    for field in ("requirements", "findings", "missing_tests", "residual_risks"):
        if not isinstance(payload.get(field), list):
            return False

    required_ids = {item.id for item in revision.requirements if item.required}
    observed_ids: set[str] = set()
    for item in payload["requirements"]:
        if not isinstance(item, dict):
            return False
        requirement_id = str(item.get("requirement_id") or "").strip()
        status = str(item.get("status") or "").strip()
        if (
            not requirement_id
            or requirement_id in observed_ids
            or status not in {"satisfied", "partial", "missing", "not_applicable"}
        ):
            return False
        observed_ids.add(requirement_id)

    for finding in payload["findings"]:
        if not isinstance(finding, dict) or not str(finding.get("problem") or "").strip():
            return False
        severity = str(finding.get("severity") or "medium").strip()
        if severity not in {"blocker", "high", "medium", "low"}:
            return False

    if any(not isinstance(item, str) for item in payload["missing_tests"]):
        return False
    if any(not isinstance(item, str) for item in payload["residual_risks"]):
        return False
    return required_ids.issubset(observed_ids)


def _self_review_protocol_retry_limit() -> int:
    raw = str(os.environ.get("OMNIX_AGENT_SELF_REVIEW_PROTOCOL_RETRIES", "2") or "2").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 2
    return max(0, min(value, 5))


def _default_review_root(spec: AgentRunSpec) -> str:
    """Choose a review root that leaves room for repository-relative paths.

    Windows Git worktrees can reject otherwise valid repository paths when the
    temporary root already consumes most of the MAX_PATH budget. Review
    snapshots only need to be outside the active checkout, so a short sibling
    directory is a safer default on Windows. Keep the longer temp-root default
    for other platforms and retain the explicit environment override at the
    call site.
    """

    if os.name == "nt" and spec.workspace is not None:
        repository = spec.workspace.repository or spec.workspace.root
        if repository:
            try:
                return str(Path(repository).expanduser().resolve().parent / ".omnix-agent-review")
            except (OSError, RuntimeError):
                pass
    return str(Path(tempfile.gettempdir()) / "omnix-agent-review-snapshots")


def _self_review_protocol_retry_count(
    repository: PostgresAgentRunRepository,
    *,
    run_id: str,
    attempt: int,
    task_revision_id: str,
    workspace_state_id: str,
    page_size: int = 5000,
) -> int:
    """Count protocol retries for one exact quality attempt and workspace state."""

    after_sequence = 0
    count = 0
    while True:
        batch = repository.list_events(
            run_id,
            after_sequence=after_sequence,
            limit=page_size,
        )
        if not batch:
            break
        for item in batch:
            if item.event_type != "quality.self_review_protocol_retry_requested":
                continue
            payload = item.payload
            if (
                int(payload.get("quality_attempt") or 0) == attempt
                and str(payload.get("task_revision_id") or "") == task_revision_id
                and str(payload.get("workspace_state_id") or "") == workspace_state_id
            ):
                count += 1
        if len(batch) < page_size:
            break
        sequence = batch[-1].sequence
        if sequence is None or int(sequence) <= after_sequence:
            break
        after_sequence = int(sequence)
    return count


def _implementation_candidate_retry_limit() -> int:
    raw = str(os.environ.get("OMNIX_AGENT_IMPLEMENTATION_SETTLE_RETRIES", "2") or "2").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 2
    return max(0, min(value, 5))


def _implementation_candidate_retry_count(
    repository: PostgresAgentRunRepository,
    *,
    run_id: str,
    attempt: int,
    task_revision_id: str,
    page_size: int = 5000,
) -> int:
    """Count same-attempt continuations where Pi settled without a reviewable implementation."""
    after_sequence = 0
    count = 0
    while True:
        batch = repository.list_events(run_id, after_sequence=after_sequence, limit=page_size)
        if not batch:
            break
        for item in batch:
            if item.event_type != "quality.implementation_continuation_requested":
                continue
            payload = item.payload
            if (
                int(payload.get("quality_attempt") or 0) == attempt
                and str(payload.get("task_revision_id") or "") == task_revision_id
            ):
                count += 1
        if len(batch) < page_size:
            break
        sequence = batch[-1].sequence
        if sequence is None or int(sequence) <= after_sequence:
            break
        after_sequence = int(sequence)
    return count


def _implementation_candidate_failures(
    diff_artifact,
    validations=(),
    *,
    allow_browser_noop: bool = False,
) -> list[str]:
    """Return deterministic reasons why the current state is not ready for review."""
    if diff_artifact is None:
        return ["missing_run_owned_diff"]
    metadata = diff_artifact.metadata if isinstance(getattr(diff_artifact, "metadata", None), dict) else {}
    failures: list[str] = []
    conflicts = metadata.get("baseline_conflicts")
    if isinstance(conflicts, list) and conflicts:
        failures.append("run_owned_diff_conflicts_with_workspace_baseline")
    modified_paths = metadata.get("modified_paths")
    paths = modified_paths if isinstance(modified_paths, list) else []
    try:
        byte_size = int(metadata.get("byte_size") or 0)
    except (TypeError, ValueError):
        byte_size = 0
    if not (paths and byte_size > 0):
        browser_proof = allow_browser_noop and any(
            getattr(item, "validation_id", None) == "browser-validation"
            and bool(getattr(item, "success", False))
            for item in validations
        )
        if not browser_proof:
            failures.append("empty_run_owned_diff_without_already_satisfied_proof")
    return failures


def _pre_review_gate(
    revision: TaskRevision,
    validations,
    *,
    workspace_state_id: str,
    diff_artifact,
) -> tuple[str, list]:
    """Order proof gates so self-review cannot begin before implementation truth."""
    missing = missing_final_validations(revision, validations, workspace_state_id=workspace_state_id)
    if missing:
        return "validating", list(missing)
    current_validations = [
        item for item in validations
        if getattr(item, "workspace_state_id", None) == workspace_state_id
    ]
    allow_browser_noop = any(
        item.id == "browser-validation" and item.required
        for item in revision.validation_plan
    )
    candidate_failures = _implementation_candidate_failures(
        diff_artifact,
        current_validations,
        allow_browser_noop=allow_browser_noop,
    )
    if candidate_failures:
        return "implementing", candidate_failures
    return "self_review", []


def _self_review_response_text(
    events: list[AgentEvent],
    *,
    attempt: int,
    task_revision_id: str,
) -> str:
    """Select only the response emitted after this self-review request."""

    marker = -1
    for index, item in enumerate(events):
        if item.event_type != "quality.stage":
            continue
        if str(item.payload.get("stage") or "") != "self_review":
            continue
        if int(item.payload.get("attempt") or 0) != attempt:
            continue
        if str(item.payload.get("task_revision_id") or "") != task_revision_id:
            continue
        marker = index
    if marker < 0:
        return ""
    return next(
        (
            str(item.payload.get("text") or "").strip()
            for item in reversed(events[marker + 1 :])
            if item.event_type == "model.message"
            and item.payload.get("phase") in {"message_end", "turn_end"}
            and str(item.payload.get("text") or "").strip()
        ),
        "",
    )


def _self_review_response_from_repository(
    repository: PostgresAgentRunRepository,
    *,
    run_id: str,
    attempt: int,
    task_revision_id: str,
    workspace_state_id: str,
    page_size: int = 5000,
) -> str:
    """Read only the response emitted inside the exact self-review stage window.

    Every quality-stage marker closes the previous window. Only the most recent
    marker that exactly matches revision, attempt, and workspace state can make
    subsequent terminal assistant text eligible as self-review evidence. This
    prevents a later retry/state/phase from being attributed to stale review
    identity.
    """

    after_sequence = 0
    response = ""
    marker_seen = False
    while True:
        batch = repository.list_events(
            run_id,
            after_sequence=after_sequence,
            limit=page_size,
        )
        if not batch:
            break
        for item in batch:
            if item.event_type == "quality.stage":
                marker_seen = (
                    str(item.payload.get("stage") or "") == "self_review"
                    and int(item.payload.get("attempt") or 0) == attempt
                    and str(item.payload.get("task_revision_id") or "") == task_revision_id
                    and str(item.payload.get("workspace_state_id") or "") == workspace_state_id
                )
                response = ""
                continue
            if (
                marker_seen
                and item.event_type == "model.message"
                and item.payload.get("phase") in {"message_end", "turn_end"}
            ):
                text = str(item.payload.get("text") or "").strip()
                if text:
                    response = text
        sequence = batch[-1].sequence
        if len(batch) < page_size or sequence is None or int(sequence) <= after_sequence:
            break
        after_sequence = int(sequence)
    return response if marker_seen else ""


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

    def _supervise_once(self) -> None:
        # Review reconciliation is idempotent and now also drives same-snapshot
        # reviewer runtime/protocol retries, not only orphan recovery.
        reconcile_orphaned_quality_reviews(self)
        super()._supervise_once()

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
        """Start a narrowed child under a durable parent resource grant."""

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
            parent_usage = repository.get_usage(parent_run_id)
            grants = PostgresResourceGrantRepository(work.connection, self.context)
            protected_fraction = (
                parent.spec.quality_reserve_fraction
                if self._quality_enabled(parent.spec)
                else 0.0
            )
            grants.assert_can_grant(
                parent,
                child_spec.limits,
                parent_usage=parent_usage,
                protected_fraction=protected_fraction,
            )
            issued = self._prepare_workspace(
                self._bind_github_repository_authority(child_spec)
            )
            snapshot = self._persist_starting_run(repository, issued)
            grants.add_grant(
                parent_run_id=parent_run_id,
                child_run_id=issued.run_id,
                limits=issued.limits,
            )
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
                    stage="inspect",
                    attempt=1,
                    task_revision_id=revision.revision_id,
                )
                repository.append_event(
                    AgentEvent(
                        run_id=issued.run_id,
                        event_type="quality.stage",
                        payload={
                            "stage": "inspect",
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

    def self_review_results(self, run_id: str):
        with unit_of_work(self.database) as work:
            rows = PostgresCodingQualityRepository(work.connection, self.context).list_self_review_results(run_id)
            work.rollback()
        return rows

    def review_results(self, run_id: str):
        with unit_of_work(self.database) as work:
            rows = PostgresCodingQualityRepository(work.connection, self.context).list_review_results(run_id)
            work.rollback()
        return rows

    def review_attempts(self, run_id: str):
        with unit_of_work(self.database) as work:
            rows = PostgresCodingQualityRepository(work.connection, self.context).list_review_attempts(run_id)
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
            self._dispatch_pending_quality_commands(command.run_id, include_parent=True)
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
                        stage="inspect",
                        attempt=1,
                        task_revision_id=revision.revision_id,
                    )
                    repository.append_event(
                        AgentEvent(
                            run_id=current.run_id,
                            event_type="quality.stage",
                            payload={
                                "stage": "inspect",
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
        current_result = self.get(result.run_id) or result
        self._dispatch_pending_quality_commands(command.run_id, include_parent=True)
        return current_result

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
        log_agent_activity(
            "quality.stage.transition_requested",
            category="quality",
            run_id=run_id,
            fields={
                "stage": stage,
                "attempt": attempt,
                "task_revision_id": task_revision_id,
                "workspace_state_id": workspace_state_id,
                "reason": reason,
            },
        )
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
        log_agent_activity(
            "quality.stage.transition_recorded",
            category="quality",
            run_id=run_id,
            fields={
                "stage": stage,
                "attempt": attempt,
                "task_revision_id": task_revision_id,
                "workspace_state_id": workspace_state_id,
            },
        )

    def _record_workspace_tool_result(self, event: AgentEvent) -> None:
        log_agent_activity(
            "quality.tool_result.received",
            category="quality",
            run_id=event.run_id,
            fields={
                "tool_call_id": event.payload.get("tool_call_id"),
                "tool": event.payload.get("tool"),
                "is_error": event.payload.get("is_error"),
                "task_revision_id": event.payload.get("task_revision_id"),
            },
        )
        call_id = str(event.payload.get("tool_call_id") or "")
        if not call_id:
            log_agent_activity(
                "quality.tool_result.unbound",
                category="quality",
                level="warning",
                run_id=event.run_id,
                fields={"reason": "missing_tool_call_id"},
            )
            return
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            current = repository.get_run(event.run_id)
            if current is None or current.status in _TERMINAL or not self._quality_enabled(current.spec):
                log_agent_activity(
                    "quality.tool_result.ignored",
                    category="quality",
                    level="debug",
                    run_id=event.run_id,
                    fields={
                        "found": current is not None,
                        "status": current.status if current is not None else None,
                        "quality_enabled": self._quality_enabled(current.spec) if current is not None else None,
                    },
                )
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
            capability_id = str(args.get("capability_id") or event.payload.get("capability_id") or "").strip()
            quality = PostgresCodingQualityRepository(work.connection, self.context)
            stage_state = quality.get_stage(event.run_id) or {}
            stage_now = str(stage_state.get("stage") or "")
            attempt = max(1, int(stage_state.get("attempt") or 1))
            revision_key = stage_state.get("task_revision_id")
            if stage_now == "inspect" and tool in {"read", "ls", "grep"}:
                self._set_quality_stage(
                    repository,
                    run_id=event.run_id,
                    stage="planning",
                    attempt=attempt,
                    task_revision_id=str(revision_key) if revision_key else None,
                    reason="repository_inspection_observed",
                )
                stage_now = "planning"
            if stage_now in {"inspect", "planning"} and tool in {"edit", "write"}:
                self._set_quality_stage(
                    repository,
                    run_id=event.run_id,
                    stage="implementing",
                    attempt=attempt,
                    task_revision_id=str(revision_key) if revision_key else None,
                    reason="first_workspace_mutation_observed",
                )
            mutating_or_validation = (
                tool in {"edit", "write", "bash", "powershell"}
                or validation_kind_for_command(command) is not None
                or validation_kind_for_capability(capability_id) is not None
            )
            if not mutating_or_validation:
                work.commit()
                return
            revision = self._current_revision(repository, event.run_id)
            active_revision_id = revision.revision_id if revision is not None else None
            event_revision_id = event.payload.get("task_revision_id")
            bound_revision_id = str(event_revision_id) if event_revision_id else active_revision_id
            state = capture_workspace_state(current.spec, task_revision_id=bound_revision_id)
            if state is None:
                log_agent_activity(
                    "quality.workspace_state.unavailable",
                    category="quality",
                    level="warning",
                    run_id=event.run_id,
                    fields={"task_revision_id": bound_revision_id, "tool_call_id": call_id},
                )
                work.rollback()
                return
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
                log_agent_activity(
                    "quality.validation.recorded",
                    category="quality",
                    run_id=event.run_id,
                    fields={
                        "result_id": validation.result_id,
                        "validation_id": validation.validation_id,
                        "kind": validation.kind,
                        "success": validation.success,
                        "command": validation.command,
                        "task_revision_id": validation.task_revision_id,
                        "workspace_state_id": validation.workspace_state_id,
                    },
                )
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
                            "metadata": dict(validation.metadata),
                        },
                    )
                )
            else:
                log_agent_activity(
                    "quality.validation.not_recognized",
                    category="quality",
                    level="debug",
                    run_id=event.run_id,
                    fields={
                        "tool": tool,
                        "command": command,
                        "capability_id": capability_id,
                        "task_revision_id": bound_revision_id,
                    },
                )
            work.commit()

    def _persist_runtime_event(self, event: AgentEvent) -> None:
        log_agent_activity(
            "service.runtime_event.received",
            category="service",
            run_id=event.run_id,
            fields={
                "event_id": event.event_id,
                "event_type": event.event_type,
                "sequence": event.sequence,
                "payload": event.payload,
            },
        )
        quality_message_settle = False
        if _is_terminal_self_review_message(event):
            with unit_of_work(self.database) as probe:
                current = PostgresAgentRunRepository(probe.connection, self.context).get_run(event.run_id)
                if current is not None and self._quality_enabled(current.spec):
                    stage = PostgresCodingQualityRepository(probe.connection, self.context).get_stage(event.run_id)
                    quality_message_settle = _terminal_message_settles_quality_stage(
                        event,
                        str((stage or {}).get("stage") or ""),
                    )
                probe.rollback()

        if event.event_type not in {"run.settled", "run.completed"} and not quality_message_settle:
            super()._persist_runtime_event(event)
            if event.event_type == "tool.completed":
                self._record_workspace_tool_result(event)
            self._dispatch_pending_quality_commands(event.run_id, include_parent=True)
            return

        with unit_of_work(self.database) as probe:
            current = PostgresAgentRunRepository(probe.connection, self.context).get_run(event.run_id)
            probe.rollback()
        if current is None or not self._quality_enabled(current.spec):
            super()._persist_runtime_event(event)
            self._dispatch_pending_quality_commands(event.run_id, include_parent=True)
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
                log_agent_activity(
                    "service.quality_event.persisted",
                    category="quality",
                    run_id=event.run_id,
                    fields={"event_type": event.event_type, "status": current.status},
                )
                if current.status in _TERMINAL or current.status in _BLOCKED_SETTLE:
                    work.commit()
                    if current.status in _TERMINAL:
                        self._close_terminal_runtime(event.run_id)
                    return
                post_action = self._advance_quality_on_settle(repository, current)
                latest = repository.get_run(event.run_id)
                terminal_runtime = latest is not None and latest.status in _TERMINAL
                work.commit()
                if terminal_runtime:
                    self._close_terminal_runtime(event.run_id)
        self._execute_quality_action(post_action)
        self._dispatch_pending_quality_commands(event.run_id, include_parent=True)

    def _queue_quality_resume(
        self,
        repository: PostgresAgentRunRepository,
        *,
        run_id: str,
        prompt: str,
        idempotency_key: str,
        quality_stage: str,
        quality_attempt: int,
        task_revision_id: str | None,
        workspace_state_id: str | None,
    ) -> tuple | None:
        """Persist an internal quality command before dispatching it to Pi."""

        command = AgentRunCommand(
            run_id=run_id,
            command_type="resume",
            payload={
                "message": prompt,
                "quality_stage": quality_stage,
                "quality_attempt": quality_attempt,
                "task_revision_id": task_revision_id,
                "workspace_state_id": workspace_state_id,
            },
            idempotency_key=idempotency_key,
        )
        stored, status = repository.enqueue_command_with_status(command)
        if status != "pending":
            return None
        return ("dispatch_command", stored)

    def _request_implementation_continuation(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
        revision: TaskRevision,
        *,
        attempt: int,
        workspace_state_id: str,
        failures: list[str],
        prior_stage: str,
    ) -> tuple | None:
        """Keep implementing when Pi settles before a reviewable candidate exists."""
        retries = _implementation_candidate_retry_count(
            repository,
            run_id=current.run_id,
            attempt=attempt,
            task_revision_id=revision.revision_id,
        )
        retry_limit = _implementation_candidate_retry_limit()
        if retries >= retry_limit:
            repository.append_event(
                AgentEvent(
                    run_id=current.run_id,
                    event_type="quality.implementation_candidate_exhausted",
                    payload={
                        "quality_attempt": attempt,
                        "continuations": retries,
                        "continuation_limit": retry_limit,
                        "failures": list(failures),
                        "task_revision_id": revision.revision_id,
                        "workspace_state_id": workspace_state_id,
                    },
                )
            )
            return self._quality_fail(repository, current, "quality_failed:implementation_candidate_not_ready")

        continuation = retries + 1
        repository.append_event(
            AgentEvent(
                run_id=current.run_id,
                event_type="quality.implementation_continuation_requested",
                payload={
                    "quality_attempt": attempt,
                    "continuation": continuation,
                    "continuation_limit": retry_limit,
                    "failures": list(failures),
                    "task_revision_id": revision.revision_id,
                    "workspace_state_id": workspace_state_id,
                },
            )
        )
        next_stage = "repairing" if prior_stage == "repairing" else "implementing"
        self._set_quality_stage(
            repository,
            run_id=current.run_id,
            stage=next_stage,
            attempt=attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=workspace_state_id,
            reason=f"implementation_candidate_not_ready_{continuation}",
        )
        prompt = (
            f"Omnix does not yet have a reviewable implementation candidate for quality attempt {attempt}. "
            f"Authoritative objective: {revision.effective_objective}\n"
            f"Candidate gate failures: {', '.join(failures)}\n"
            "Do not self-review or declare completion. Re-read the authoritative objective, inspect the actual "
            "target surface and current diff, and carry out the requested implementation now. Make only task-scoped "
            "changes. If this is a user-visible UI task, locate the exact control/surface and verify the requested "
            "visible outcome with governed browser evidence. Then inspect the complete diff and run the required "
            "final-state validation before settling."
        )
        return self._queue_quality_resume(
            repository,
            run_id=current.run_id,
            prompt=prompt,
            idempotency_key=(
                f"quality-implementation-continuation:{current.run_id}:{revision.revision_id}:"
                f"{attempt}:{continuation}"
            ),
            quality_stage=next_stage,
            quality_attempt=attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=workspace_state_id,
        )

    def _request_self_review_protocol_retry(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
        revision: TaskRevision,
        quality: PostgresCodingQualityRepository,
        *,
        attempt: int,
        workspace_state_id: str,
        response_text: str,
    ) -> tuple | None:
        """Retry a missing/malformed verdict without consuming a repair attempt."""

        retries = _self_review_protocol_retry_count(
            repository,
            run_id=current.run_id,
            attempt=attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=workspace_state_id,
        )
        retry_limit = _self_review_protocol_retry_limit()
        if retries >= retry_limit:
            repository.append_event(
                AgentEvent(
                    run_id=current.run_id,
                    event_type="quality.self_review_protocol_exhausted",
                    payload={
                        "quality_attempt": attempt,
                        "protocol_retries": retries,
                        "protocol_retry_limit": retry_limit,
                        "response_present": bool(str(response_text or "").strip()),
                        "task_revision_id": revision.revision_id,
                        "workspace_state_id": workspace_state_id,
                    },
                )
            )
            return self._quality_fail(
                repository,
                current,
                "quality_failed:quality_self_review_protocol_exhausted",
            )

        protocol_retry = retries + 1
        validations = quality.list_validation_results(
            current.run_id,
            task_revision_id=revision.revision_id,
        )
        current_validations = [
            item for item in validations if item.workspace_state_id == workspace_state_id
        ]
        repository.append_event(
            AgentEvent(
                run_id=current.run_id,
                event_type="quality.self_review_protocol_retry_requested",
                payload={
                    "quality_attempt": attempt,
                    "protocol_retry": protocol_retry,
                    "protocol_retry_limit": retry_limit,
                    "response_present": bool(str(response_text or "").strip()),
                    "task_revision_id": revision.revision_id,
                    "workspace_state_id": workspace_state_id,
                },
            )
        )
        self._set_quality_stage(
            repository,
            run_id=current.run_id,
            stage="self_review",
            attempt=attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=workspace_state_id,
            reason=f"self_review_protocol_retry_{protocol_retry}",
        )
        failure_kind = (
            "no assistant verdict text"
            if not str(response_text or "").strip()
            else "a response that did not satisfy the structured self-review schema"
        )
        prompt = self_review_prompt(
            revision,
            attempt=attempt,
            validations=current_validations,
        )
        prompt += (
            f"\n\nInternal protocol retry {protocol_retry}/{retry_limit}: the previous "
            f"self-review turn produced {failure_kind}. This is transport/protocol "
            "recovery, not a new implementation quality attempt. Do not edit files, "
            "rerun tools, or send progress prose. Return exactly one complete JSON "
            "object matching the required schema now."
        )
        return self._queue_quality_resume(
            repository,
            run_id=current.run_id,
            prompt=prompt,
            idempotency_key=(
                f"quality-self-review-protocol:{current.run_id}:{revision.revision_id}:"
                f"{workspace_state_id}:{attempt}:{protocol_retry}"
            ),
            quality_stage="self_review",
            quality_attempt=attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=workspace_state_id,
        )

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
                desired_state="cancelled",
                last_error="quality_task_revision_unavailable",
            )
            return None
        quality = PostgresCodingQualityRepository(repository.connection, self.context)
        stage_state = quality.get_stage(current.run_id) or {
            "stage": "inspect",
            "attempt": 1,
            "task_revision_id": revision.revision_id,
            "workspace_state_id": None,
        }
        stage = str(stage_state.get("stage") or "implementing")
        attempt = max(1, int(stage_state.get("attempt") or 1))

        if stage in {"inspect", "planning", "implementing", "repairing", "validating"}:
            state = capture_workspace_state(current.spec, task_revision_id=revision.revision_id)
            if state is None:
                return self._quality_fail(repository, current, "quality_workspace_state_unavailable")
            quality.add_workspace_state(state)
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
            validations = quality.list_validation_results(
                current.run_id,
                task_revision_id=revision.revision_id,
            )
            current_validations = [
                item for item in validations if item.workspace_state_id == state.state_id
            ]
            gate, gate_details = _pre_review_gate(
                revision,
                validations,
                workspace_state_id=state.state_id,
                diff_artifact=diff_artifact,
            )
            if gate == "validating":
                self._set_quality_stage(
                    repository,
                    run_id=current.run_id,
                    stage="validating",
                    attempt=attempt,
                    task_revision_id=revision.revision_id,
                    workspace_state_id=state.state_id,
                    reason="implementation_candidate_requires_final_state_validation",
                )
                prompt = validation_prompt(revision, gate_details)
                validation_generation = len(current_validations)
                return self._queue_quality_resume(
                    repository,
                    run_id=current.run_id,
                    prompt=prompt,
                    idempotency_key=(
                        f"quality-validation:{current.run_id}:{state.state_id}:"
                        f"{attempt}:{validation_generation}"
                    ),
                    quality_stage="validating",
                    quality_attempt=attempt,
                    task_revision_id=revision.revision_id,
                    workspace_state_id=state.state_id,
                )
            if gate == "implementing":
                return self._request_implementation_continuation(
                    repository,
                    current,
                    revision,
                    attempt=attempt,
                    workspace_state_id=state.state_id,
                    failures=[str(item) for item in gate_details],
                    prior_stage=stage,
                )

            self._set_quality_stage(
                repository,
                run_id=current.run_id,
                stage="self_review",
                attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
                reason="validated_implementation_candidate_ready",
            )
            prompt = self_review_prompt(
                revision,
                attempt=attempt,
                validations=current_validations,
            )
            return self._queue_quality_resume(
                repository,
                run_id=current.run_id,
                prompt=prompt,
                idempotency_key=(
                    f"quality-self-review:{current.run_id}:{revision.revision_id}:"
                    f"{state.state_id}:{attempt}"
                ),
                quality_stage="self_review",
                quality_attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
            )

        state = capture_workspace_state(current.spec, task_revision_id=revision.revision_id)
        if state is None:
            return self._quality_fail(repository, current, "quality_workspace_state_unavailable")
        quality.add_workspace_state(state)

        if stage == "self_review":
            text = _self_review_response_from_repository(
                repository,
                run_id=current.run_id,
                attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
            )
            if not _self_review_payload_is_protocol_valid(text, revision):
                return self._request_self_review_protocol_retry(
                    repository,
                    current,
                    revision,
                    quality,
                    attempt=attempt,
                    workspace_state_id=state.state_id,
                    response_text=text,
                )
            self_review = parse_self_review_result(
                text,
                run_id=current.run_id,
                revision=revision,
                workspace_state_id=state.state_id,
            )
            quality.add_self_review_result(self_review)
            repository.append_event(
                AgentEvent(
                    run_id=current.run_id,
                    event_type="quality.self_review_completed",
                    payload={
                        "attempt": attempt,
                        "self_review_result_id": self_review.self_review_result_id,
                        "verdict": self_review.verdict,
                        "requirements": [item.model_dump(mode="json") for item in self_review.requirements],
                        "findings": [item.model_dump(mode="json") for item in self_review.findings],
                        "missing_tests": list(self_review.missing_tests),
                        "residual_risks": list(self_review.residual_risks),
                        "task_revision_id": revision.revision_id,
                        "workspace_state_id": state.state_id,
                    },
                )
            )
            if not self_review_is_acceptable(self_review, revision):
                return self._request_quality_repair(
                    repository,
                    current,
                    revision,
                    self_review,
                    failures=["quality_self_review_not_approved"],
                )
            self._set_quality_stage(
                repository,
                run_id=current.run_id,
                stage="validating",
                attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
            )

        validations = quality.list_validation_results(
            current.run_id,
            task_revision_id=revision.revision_id,
        )
        current_validations = [
            item for item in validations if item.workspace_state_id == state.state_id
        ]
        self_reviews = quality.list_self_review_results(
            current.run_id,
            task_revision_id=revision.revision_id,
        )
        self_review_fresh = any(
            item.workspace_state_id == state.state_id
            and self_review_is_acceptable(item, revision)
            for item in self_reviews
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
            prompt = self_review_prompt(
                revision,
                attempt=attempt,
                validations=current_validations,
            )
            return self._queue_quality_resume(
                repository,
                run_id=current.run_id,
                prompt=prompt,
                idempotency_key=f"quality-self-review-refresh:{current.run_id}:{state.state_id}:{attempt}",
                quality_stage="self_review",
                quality_attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
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
            prompt = validation_prompt(revision, missing)
            return self._queue_quality_resume(
                repository,
                run_id=current.run_id,
                prompt=prompt,
                idempotency_key=f"quality-validation:{current.run_id}:{state.state_id}:{attempt}",
                quality_stage="validating",
                quality_attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
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
            _default_review_root(current.spec),
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
        if action[0] == "dispatch_command":
            _, command = action
            try:
                self.command(command)
            except Exception:
                pass
            return
        if action[0] == "launch_reviews":
            _, parent_run_id, snapshot_id, count = action
            self._launch_reviewer_children(parent_run_id, snapshot_id, int(count))

    def _dispatch_pending_quality_commands(self, run_id: str, *, include_parent: bool = False) -> None:
        targets: list[str] = []
        pending: list[AgentRunCommand] = []
        try:
            with unit_of_work(self.database) as work:
                repository = PostgresAgentRunRepository(work.connection, self.context)
                snapshot = repository.get_run(run_id)
                if snapshot is not None:
                    targets.append(snapshot.run_id)
                    if include_parent and snapshot.spec.parent_run_id:
                        targets.append(snapshot.spec.parent_run_id)
                for target in dict.fromkeys(targets):
                    for command in repository.list_pending_commands(target):
                        if (
                            command.command_type == "resume"
                            and str(command.payload.get("quality_stage") or "")
                            in {"implementing", "repairing", "validating", "self_review"}
                        ):
                            pending.append(command)
                work.rollback()
        except Exception:
            return

        seen: set[str] = set()
        for command in pending:
            if command.command_id in seen:
                continue
            seen.add(command.command_id)
            self._execute_quality_action(("dispatch_command", command))

    def _launch_reviewer_children(self, parent_run_id: str, snapshot_id: str, count: int) -> None:
        launch_reviewer_children(self, parent_run_id, snapshot_id, count)

    @staticmethod
    def _review_snapshot_id_from_child(child: AgentRunSnapshot) -> str | None:
        return review_snapshot_id_from_child(child)

    def _review_result_from_child(
        self,
        repository: PostgresAgentRunRepository,
        child: AgentRunSnapshot,
        snapshot: ReviewSnapshot,
    ) -> ReviewResult | None:
        """Compatibility reader that returns substantive review evidence only.

        Runtime/protocol failure is represented by ReviewAttempt and therefore
        returns ``None`` here instead of fabricating a blocked ReviewResult.
        """

        if child.status != "completed":
            return None
        revision = self._current_revision(
            repository,
            child.spec.parent_run_id or snapshot.run_id,
        )
        if revision is None or revision.revision_id != snapshot.task_revision_id:
            return None
        text = latest_reviewer_text(
            repository.list_events(child.run_id, after_sequence=0, limit=5000)
        )
        if not review_payload_is_protocol_valid(text, revision):
            return None
        result = parse_review_result(
            text,
            parent_run_id=child.spec.parent_run_id or snapshot.run_id,
            reviewer_run_id=child.run_id,
            snapshot=snapshot,
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
        if finalize_reviewer_child_in_repository(self, repository, child_run_id):
            return
        super()._maybe_finalize_parent_in_repository(repository, child_run_id)

    def _request_quality_workspace_refresh(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
        revision: TaskRevision,
        *,
        current_workspace_state_id: str,
        prior_workspace_state_id: str,
    ) -> tuple | None:
        """Refresh exact-state quality evidence without consuming a repair attempt.

        A workspace can change after independent review because the checkout was
        updated or another authorized actor changed it. That invalidates the old
        validation/self-review/review evidence, but it is not itself substantive
        evidence that the implementation is wrong. Revalidate the new exact state
        on the same quality attempt; any later real finding may still request the
        bounded repair loop.
        """

        quality = PostgresCodingQualityRepository(repository.connection, self.context)
        stage = quality.get_stage(current.run_id) or {"attempt": 1}
        attempt = max(1, int(stage.get("attempt") or 1))
        validations = quality.list_validation_results(
            current.run_id,
            task_revision_id=revision.revision_id,
        )
        missing = missing_final_validations(
            revision,
            validations,
            workspace_state_id=current_workspace_state_id,
        )
        if not missing:
            missing = [item for item in revision.validation_plan if item.required]
        self._set_quality_stage(
            repository,
            run_id=current.run_id,
            stage="validating",
            attempt=attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=current_workspace_state_id,
            reason="workspace_changed_after_independent_review",
        )
        latest = repository.get_run(current.run_id) or current
        if latest.status != "running":
            repository.update_state(
                current.run_id,
                expected_revision=latest.revision,
                status="running",
                desired_state="running",
                worker_id=self.worker_id,
                last_error=None,
            )
        prompt = validation_prompt(revision, missing)
        prompt += (
            "\n\nOmnix detected that the workspace changed after the prior independent review. "
            f"Reviewed workspace state: {prior_workspace_state_id}. Current workspace state: "
            f"{current_workspace_state_id}. The prior validation, self-review, and independent review are "
            "stale by exact-state identity, but this is not a substantive implementation defect and does "
            "not consume a quality repair attempt. Do not mutate merely to make the state IDs match. "
            "Validate the current state against the authoritative task. If validation proves a real "
            "implementation change is needed, inspect the new evidence and amend the active plan before "
            "any mutation. Otherwise finish the requested validation so Omnix can self-review and "
            "independently review this exact current state."
        )
        return self._queue_quality_resume(
            repository,
            run_id=current.run_id,
            prompt=prompt,
            idempotency_key=(
                f"quality-workspace-refresh:{current.run_id}:{revision.revision_id}:"
                f"{current_workspace_state_id}:{attempt}"
            ),
            quality_stage="validating",
            quality_attempt=attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=current_workspace_state_id,
        )

    def _request_quality_repair(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
        revision: TaskRevision,
        review: ReviewResult | SelfReviewResult | None,
        *,
        failures: list[str],
    ) -> tuple | None:
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
            return None
        next_attempt = attempt + 1
        state_id = stage.get("workspace_state_id")
        validations = quality.list_validation_results(
            current.run_id,
            task_revision_id=revision.revision_id,
        )
        missing = (
            missing_final_validations(
                revision,
                validations,
                workspace_state_id=str(state_id or ""),
            )
            if state_id
            else list(revision.validation_plan)
        )
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
            repository.update_state(
                current.run_id,
                expected_revision=latest.revision,
                status="running",
                desired_state="running",
                worker_id=self.worker_id,
                last_error=None,
            )
        return self._queue_quality_resume(
            repository,
            run_id=current.run_id,
            prompt=prompt,
            idempotency_key=(
                f"quality-repair:{current.run_id}:{revision.revision_id}:{next_attempt}:"
                f"{hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:16]}"
            ),
            quality_stage="repairing",
            quality_attempt=next_attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=str(state_id) if state_id else None,
        )

    def _quality_fail(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
        reason: str,
    ) -> None:
        log_agent_activity(
            "quality.failed",
            category="quality",
            level="error",
            run_id=current.run_id,
            fields={"reason": reason, "status_before": current.status, "revision": current.revision},
        )
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
        acceptance_stage = quality.get_stage(current.run_id) or {}
        reviewed_workspace_state_id = (
            str(acceptance_stage.get("workspace_state_id") or "").strip() or None
        )
        state = capture_workspace_state(current.spec, task_revision_id=revision_id)
        if state is not None:
            quality.add_workspace_state(state)
        workspace_changed_after_review = bool(
            str(acceptance_stage.get("stage") or "") == "acceptance"
            and reviewed_workspace_state_id
            and state is not None
            and state.state_id != reviewed_workspace_state_id
        )
        validations = quality.list_validation_results(current.run_id, task_revision_id=revision_id)
        reviews = quality.list_review_results(current.run_id, task_revision_id=revision_id)
        self_reviews = quality.list_self_review_results(current.run_id, task_revision_id=revision_id)
        quality_failures = quality_failure_reasons(current, revision, state, validations, reviews, self_reviews)
        planning_assessment = evaluate_planning_acceptance(
            repository.connection,
            self.context,
            current,
            revision,
        )
        repository.append_event(
            AgentEvent(
                run_id=current.run_id,
                event_type="planning.conformance_evaluated",
                payload={
                    "mode": planning_assessment.mode,
                    "plan_revision_id": planning_assessment.plan_revision_id,
                    "would_block": planning_assessment.would_block,
                    "blocks_acceptance": planning_assessment.blocks_acceptance,
                    "fail_closed": planning_assessment.fail_closed,
                    "failures": list(planning_assessment.failures),
                    "task_revision_id": revision_id,
                    "workspace_state_id": state.state_id if state else None,
                },
            )
        )

        non_reviewer_children = [
            child for child in repository.list_children(current.run_id)
            if child.spec.profile != "coding-reviewer"
        ]
        children_terminal = all(child.status in _TERMINAL for child in non_reviewer_children)
        child_failed = any(child.status in {"failed", "cancelled"} for child in non_reviewer_children)
        failures = list(result.failures) + list(quality_failures)
        if workspace_changed_after_review:
            failures.append("quality_workspace_changed_after_review")
        if planning_assessment.blocks_acceptance:
            failures.extend(planning_assessment.failures)
        if not children_terminal:
            failures.append("children_not_terminal")
        if child_failed:
            failures.append("child_run_failed")
        failures = list(dict.fromkeys(failures))
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
                    "planning": {
                        "mode": planning_assessment.mode,
                        "plan_revision_id": planning_assessment.plan_revision_id,
                        "would_block": planning_assessment.would_block,
                        "blocks_acceptance": planning_assessment.blocks_acceptance,
                        "fail_closed": planning_assessment.fail_closed,
                        "failures": list(planning_assessment.failures),
                    },
                },
            )
        )
        latest = repository.get_run(current.run_id) or current
        if workspace_changed_after_review:
            if planning_assessment.blocks_acceptance:
                self._quality_fail(
                    repository,
                    latest,
                    "review_integrity_failed:workspace_changed_after_review:"
                    + ",".join(planning_assessment.failures),
                )
                return
            if revision is None or state is None or reviewed_workspace_state_id is None:
                self._quality_fail(
                    repository,
                    latest,
                    "review_integrity_failed:workspace_refresh_context_unavailable",
                )
                return
            self._request_quality_workspace_refresh(
                repository,
                latest,
                revision,
                current_workspace_state_id=state.state_id,
                prior_workspace_state_id=reviewed_workspace_state_id,
            )
            return
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
        fail_closed = planning_assessment.fail_closed or any(
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
