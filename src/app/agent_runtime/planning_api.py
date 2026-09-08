"""Server-authoritative API for evidence-backed coding planning."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.persistence.unit_of_work import unit_of_work

from .coding_quality_repository import PostgresCodingQualityRepository
from .planning import (
    build_inspection_bundle,
    build_plan_authority,
    capture_planning_baseline,
    classify_operation_effect,
    derive_planning_lenses,
    engineering_contract_digest,
    inspection_evidence_digest,
    operation_plan_failures,
    plan_conformance_failures,
    plan_gate_failures,
    planned_paths,
    planning_mode,
)
from .planning_contracts import (
    ImplementationPlanRevision,
    ImplementationPlanSubmission,
    PlanningDecision,
)
from .planning_repository import PostgresPlanningRepository
from .repository import PostgresAgentRunRepository
from .repository_guidance import compile_repository_guidance
from .service import default_agent_run_service

router = APIRouter(prefix="/api/agent-runs", tags=["agent-planning"])


class PlanningInspectRequest(BaseModel):
    queries: list[str] = Field(default_factory=list, max_length=16)
    paths: list[str] = Field(default_factory=list, max_length=16)


class PlanningSubmitRequest(BaseModel):
    plan: ImplementationPlanSubmission


class PlanningAuthorizeRequest(BaseModel):
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)
    path: str | None = None
    command: str | None = None


def _load(service, run_id: str):
    snapshot = service.get(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")
    if snapshot.spec.profile != "coding" or "diff" not in snapshot.spec.expected_artifacts:
        raise HTTPException(status_code=409, detail="agent_planning_not_applicable")
    return snapshot


def _current_revision(service, repository: PostgresAgentRunRepository, run_id: str):
    revision = service._current_revision(repository, run_id)  # internal runtime module
    if revision is None:
        raise HTTPException(status_code=409, detail="agent_planning_task_revision_unavailable")
    return revision


def _repository_guidance_digest(snapshot, revision, plan) -> str | None:
    if plan is None:
        return None
    _, digest = compile_repository_guidance(
        snapshot.spec.workspace,
        objective=revision.effective_objective,
        relevant_paths=planned_paths(plan),
    )
    return digest


def _plan_freshness_failures(
    plan,
    revision,
    evidence_digest: str,
    repository_guidance_digest: str | None = None,
) -> list[str]:
    """Return authority-identity failures independently of operation effect."""

    if plan is None:
        return ["approved_plan_missing"]
    failures: list[str] = []
    if plan.status != "approved":
        failures.append(f"plan_not_approved:{plan.status}")
    if plan.task_revision_id != revision.revision_id:
        failures.append("plan_task_revision_stale")
    if plan.authority.engineering_contract_digest != engineering_contract_digest(revision):
        failures.append("plan_engineering_contract_stale")
    if plan.authority.inspection_evidence_digest != evidence_digest:
        failures.append("plan_inspection_evidence_stale")
    if (
        plan.authority.repository_guidance_digest is not None
        and repository_guidance_digest is not None
        and plan.authority.repository_guidance_digest != repository_guidance_digest
    ):
        failures.append("plan_repository_guidance_stale")
    return failures


def _planning_state_should_stale(reasons: list[str]) -> bool:
    """Only authority drift may stale an approved plan.

    An attempted off-plan mutation is itself useful shadow/enforce telemetry, but
    it does not change the TaskRevision, inspection evidence, or planning
    baseline. Turning such an attempted operation into a durable stale state
    would let a model mistake poison an otherwise valid plan.
    """

    authority_drift = {
        "plan_task_revision_stale",
        "plan_engineering_contract_stale",
        "plan_inspection_evidence_stale",
        "plan_repository_guidance_stale",
        "planning_state_task_revision_stale",
        "planning_active_plan_identity_mismatch",
        "planning_base_commit_changed",
    }
    return any(
        reason in authority_drift or reason.startswith("preexisting_dirty_path_modified:")
        for reason in reasons
    )


def _planning_state_status_after_submission(
    plan_status: str,
    active_plan_revision_id: str | None,
) -> str:
    """A rejected proposal must not revoke a still-valid approved plan."""

    if plan_status == "approved" or active_plan_revision_id:
        return "approved"
    return plan_status


def _ordered_union(left, right):
    output = list(left)
    for item in right:
        if item not in output:
            output.append(item)
    return output


def _merge_plan_delta(
    previous: ImplementationPlanRevision,
    delta: ImplementationPlanSubmission,
) -> ImplementationPlanSubmission:
    """Resolve an immutable PlanDelta into cumulative effective authority.

    A PlanDelta is intentionally incremental: omitted entries continue to be
    authorized by the previously approved revision. Entries with the same
    identity refine that prior entry without discarding previously authorized
    paths/coverage. Candidate dispositions are the exception because a newer
    semantic classification supersedes the older disposition for that exact
    candidate.
    """

    coverage = {item.requirement_id: item for item in previous.requirement_coverage}
    coverage_order = [item.requirement_id for item in previous.requirement_coverage]
    for item in delta.requirement_coverage:
        prior = coverage.get(item.requirement_id)
        if prior is None:
            coverage_order.append(item.requirement_id)
            coverage[item.requirement_id] = item
        else:
            coverage[item.requirement_id] = prior.model_copy(update={
                "plan_item_ids": _ordered_union(prior.plan_item_ids, item.plan_item_ids),
                "validation_ids": _ordered_union(prior.validation_ids, item.validation_ids),
            })

    impacts = {item.candidate_id: item for item in previous.impacts}
    impact_order = [item.candidate_id for item in previous.impacts]
    for item in delta.impacts:
        if item.candidate_id not in impacts:
            impact_order.append(item.candidate_id)
        impacts[item.candidate_id] = item

    changes = {item.id: item for item in previous.changes}
    change_order = [item.id for item in previous.changes]
    for item in delta.changes:
        prior = changes.get(item.id)
        if prior is None:
            change_order.append(item.id)
            changes[item.id] = item
        else:
            changes[item.id] = prior.model_copy(update={
                "intent": item.intent,
                "paths": _ordered_union(prior.paths, item.paths),
                "requirement_ids": _ordered_union(prior.requirement_ids, item.requirement_ids),
                "candidate_ids": _ordered_union(prior.candidate_ids, item.candidate_ids),
                "validation_ids": _ordered_union(prior.validation_ids, item.validation_ids),
                "allowed_effects": _ordered_union(prior.allowed_effects, item.allowed_effects),
                "command_hints": _ordered_union(prior.command_hints, item.command_hints),
            })

    validations = {item.id: item for item in previous.validations}
    validation_order = [item.id for item in previous.validations]
    for item in delta.validations:
        prior = validations.get(item.id)
        if prior is None:
            validation_order.append(item.id)
            validations[item.id] = item
        else:
            validations[item.id] = prior.model_copy(update={
                "kind": item.kind,
                "requirement_ids": _ordered_union(prior.requirement_ids, item.requirement_ids),
                "invariant": item.invariant if item.invariant is not None else prior.invariant,
                "command_hint": item.command_hint if item.command_hint is not None else prior.command_hint,
            })

    hypotheses = {item.hypothesis: item for item in previous.causal_hypotheses}
    hypothesis_order = [item.hypothesis for item in previous.causal_hypotheses]
    for item in delta.causal_hypotheses:
        if item.hypothesis not in hypotheses:
            hypothesis_order.append(item.hypothesis)
        hypotheses[item.hypothesis] = item

    return ImplementationPlanSubmission(
        previous_plan_revision_id=previous.plan_revision_id,
        planning_lenses=_ordered_union(previous.planning_lenses, delta.planning_lenses),
        requirement_coverage=[coverage[key] for key in coverage_order],
        impacts=[impacts[key] for key in impact_order],
        changes=[changes[key] for key in change_order],
        validations=[validations[key] for key in validation_order],
        assumptions=_ordered_union(previous.assumptions, delta.assumptions),
        blockers=_ordered_union(previous.blockers, delta.blockers),
        causal_hypotheses=[hypotheses[key] for key in hypothesis_order],
    )


def _inspection_response(mode, revision, evidence, candidates, lenses, state):
    return {
        "mode": mode,
        "task_revision_id": revision.revision_id,
        "planning_lenses": list(lenses),
        "requirements": [item.model_dump(mode="json") for item in revision.requirements],
        "validation_plan": [item.model_dump(mode="json") for item in revision.validation_plan],
        "inspection_evidence": [item.model_dump(mode="json") for item in evidence],
        "impact_candidates": [item.model_dump(mode="json") for item in candidates],
        "inspection_evidence_digest": inspection_evidence_digest(evidence),
        "planning_state": state,
    }


def _lock_planning_state(work, workspace_id: str, run_id: str) -> None:
    work.connection.execute(
        """
        SELECT run_id
          FROM omnix_agent_planning_state
         WHERE workspace_id = %s AND run_id = %s
         FOR UPDATE
        """,
        (workspace_id, run_id),
    ).fetchone()


def _unknown_command_is_explicitly_planned(plan, command: str) -> bool:
    if plan is None or not command.strip():
        return False
    normalized = command.strip().casefold()
    return any(
        "unknown" in item.allowed_effects
        and any(normalized.startswith(hint.strip().casefold()) for hint in item.command_hints if hint.strip())
        for item in plan.changes
    )


@router.post("/{run_id}/planning/inspect")
def inspect_agent_plan(run_id: str, request: PlanningInspectRequest) -> dict[str, Any]:
    service = default_agent_run_service()
    snapshot = _load(service, run_id)
    mode = planning_mode()
    with unit_of_work(service.database) as work:
        runs = PostgresAgentRunRepository(work.connection, service.context)
        planning = PostgresPlanningRepository(work.connection, service.context)
        revision = _current_revision(service, runs, run_id)
        fresh_evidence, fresh_candidates, lenses = build_inspection_bundle(
            snapshot.spec,
            revision,
            queries=request.queries,
            paths=request.paths,
        )
        for item in fresh_evidence:
            planning.add_inspection_evidence(item)
        for item in fresh_candidates:
            planning.add_impact_candidate(item)
        evidence = planning.list_inspection_evidence(run_id, task_revision_id=revision.revision_id)
        candidates = planning.list_impact_candidates(run_id, task_revision_id=revision.revision_id)
        state = planning.get_state(run_id)
        if (
            state is None
            or state.get("task_revision_id") != revision.revision_id
            or not state.get("planning_baseline_id")
        ):
            baseline_id, baseline = capture_planning_baseline(snapshot.spec)
            state = planning.set_state(
                run_id,
                mode=mode,
                task_revision_id=revision.revision_id,
                status="required",
                latest_plan_revision_id=None,
                active_plan_revision_id=None,
                planning_baseline_id=baseline_id,
                baseline_provenance=baseline,
            )
        elif state.get("mode") != mode:
            state = planning.set_state(
                run_id,
                mode=mode,
                task_revision_id=revision.revision_id,
                status=str(state.get("status") or "required"),
                latest_plan_revision_id=(
                    str(state.get("latest_plan_revision_id"))
                    if state.get("latest_plan_revision_id") else None
                ),
                active_plan_revision_id=(
                    str(state.get("active_plan_revision_id"))
                    if state.get("active_plan_revision_id") else None
                ),
                planning_baseline_id=(
                    str(state.get("planning_baseline_id"))
                    if state.get("planning_baseline_id") else None
                ),
                baseline_provenance=dict(state.get("baseline_provenance") or {}),
            )
        active_id = str(state.get("active_plan_revision_id") or "") if state else ""
        active_plan = planning.get_plan(run_id, active_id) if active_id else None
        current_digest = inspection_evidence_digest(evidence)
        guidance_digest = _repository_guidance_digest(snapshot, revision, active_plan)
        freshness = _plan_freshness_failures(
            active_plan,
            revision,
            current_digest,
            guidance_digest,
        ) if active_plan is not None else []
        if active_plan is not None and freshness:
            state = planning.set_state(
                run_id,
                mode=mode,
                task_revision_id=revision.revision_id,
                status="stale",
                latest_plan_revision_id=(
                    str(state.get("latest_plan_revision_id"))
                    if state and state.get("latest_plan_revision_id") else None
                ),
                active_plan_revision_id=active_plan.plan_revision_id,
                planning_baseline_id=active_plan.authority.planning_baseline_id,
                baseline_provenance=dict(active_plan.baseline_provenance),
            )
        response = _inspection_response(mode, revision, evidence, candidates, lenses, state)
        work.commit()
    return response


def _submit_plan(run_id: str, request: PlanningSubmitRequest, *, amend: bool) -> dict[str, Any]:
    service = default_agent_run_service()
    snapshot = _load(service, run_id)
    mode = planning_mode()
    with unit_of_work(service.database) as work:
        runs = PostgresAgentRunRepository(work.connection, service.context)
        quality = PostgresCodingQualityRepository(work.connection, service.context)
        planning = PostgresPlanningRepository(work.connection, service.context)
        revision = _current_revision(service, runs, run_id)
        state = planning.get_state(run_id)
        if state is None or state.get("task_revision_id") != revision.revision_id:
            baseline_id, baseline = capture_planning_baseline(snapshot.spec)
            state = planning.set_state(
                run_id,
                mode=mode,
                task_revision_id=revision.revision_id,
                status="required",
                latest_plan_revision_id=None,
                active_plan_revision_id=None,
                planning_baseline_id=baseline_id,
                baseline_provenance=baseline,
            )

        # Serialize plan lineage and sequence allocation for this run. This
        # closes duplicate/retry races where two concurrent submissions could
        # both extend the same revision or claim the same sequence number.
        _lock_planning_state(work, service.context.workspace_id, run_id)
        state = planning.get_state(run_id) or state
        active_id = str(state.get("active_plan_revision_id") or "") or None

        previous = None
        previous_id = request.plan.previous_plan_revision_id
        if amend:
            if not active_id:
                raise HTTPException(status_code=409, detail="agent_plan_amend_requires_active_revision")
            if previous_id and previous_id != active_id:
                raise HTTPException(status_code=409, detail="agent_plan_amend_must_extend_active_revision")
            previous_id = active_id
            previous = planning.get_plan(run_id, previous_id)
            if previous is None or previous.task_revision_id != revision.revision_id:
                raise HTTPException(status_code=409, detail="agent_plan_previous_revision_stale")
        else:
            if previous_id:
                raise HTTPException(status_code=422, detail="agent_plan_submit_must_not_set_previous_revision")
            if active_id:
                raise HTTPException(status_code=409, detail="agent_plan_submit_requires_amend")

        evidence = planning.list_inspection_evidence(run_id, task_revision_id=revision.revision_id)
        candidates = planning.list_impact_candidates(run_id, task_revision_id=revision.revision_id)
        if not evidence:
            fresh_evidence, fresh_candidates, _ = build_inspection_bundle(snapshot.spec, revision)
            for item in fresh_evidence:
                planning.add_inspection_evidence(item)
            for item in fresh_candidates:
                planning.add_impact_candidate(item)
            evidence = planning.list_inspection_evidence(run_id, task_revision_id=revision.revision_id)
            candidates = planning.list_impact_candidates(run_id, task_revision_id=revision.revision_id)

        if previous is not None:
            baseline_id = previous.authority.planning_baseline_id
            baseline = dict(previous.baseline_provenance)
        else:
            baseline_id = str(state.get("planning_baseline_id") or "")
            baseline = dict(state.get("baseline_provenance") or {})
            if not baseline_id or not baseline:
                baseline_id, baseline = capture_planning_baseline(snapshot.spec)

        server_lenses = derive_planning_lenses(revision)
        proposed = request.plan.model_copy(update={
            "previous_plan_revision_id": previous_id if amend else None,
            "planning_lenses": sorted(set(server_lenses) | set(request.plan.planning_lenses)),
        })
        submission = _merge_plan_delta(previous, proposed) if previous is not None else proposed
        paths = [path for item in submission.changes for path in item.paths]
        _, guidance_digest = compile_repository_guidance(
            snapshot.spec.workspace,
            objective=revision.effective_objective,
            relevant_paths=paths,
        )
        authority = build_plan_authority(
            revision,
            baseline_id=baseline_id,
            evidence=evidence,
            repository_guidance_digest=guidance_digest,
        )
        failures = plan_gate_failures(snapshot.spec, revision, submission, candidates, evidence)
        status = "approved" if not failures else "rejected"
        stage = quality.get_stage(run_id) or {}
        source = (
            "repair"
            if str(stage.get("stage") or "") == "repairing"
            else "delta" if amend else "initial"
        )
        plan = ImplementationPlanRevision(
            run_id=run_id,
            task_revision_id=revision.revision_id,
            sequence=planning.next_plan_sequence(run_id, revision.revision_id),
            previous_plan_revision_id=previous_id if amend else None,
            source=source,
            status=status,
            mode=mode,
            authority=authority,
            baseline_provenance=baseline,
            planning_lenses=submission.planning_lenses,
            requirement_coverage=submission.requirement_coverage,
            impacts=submission.impacts,
            changes=submission.changes,
            validations=submission.validations,
            assumptions=submission.assumptions,
            blockers=submission.blockers,
            causal_hypotheses=submission.causal_hypotheses,
            gate_failures=failures,
        )
        planning.add_plan(plan)
        active_id = (
            plan.plan_revision_id
            if status == "approved"
            else active_id
        )
        state_status = _planning_state_status_after_submission(status, active_id)
        new_state = planning.set_state(
            run_id,
            mode=mode,
            task_revision_id=revision.revision_id,
            status=state_status,
            latest_plan_revision_id=plan.plan_revision_id,
            active_plan_revision_id=active_id,
            planning_baseline_id=baseline_id,
            baseline_provenance=baseline,
        )
        work.commit()
    return {
        "mode": mode,
        "approved": status == "approved",
        "plan_revision": plan.model_dump(mode="json"),
        "gate_failures": failures,
        "planning_state": new_state,
        "next_action": (
            "implementation may proceed"
            if status == "approved"
            else "inspect the reported gaps and submit an amended plan before implementation"
        ),
    }


@router.post("/{run_id}/planning/submit")
def submit_agent_plan(run_id: str, request: PlanningSubmitRequest) -> dict[str, Any]:
    return _submit_plan(run_id, request, amend=False)


@router.post("/{run_id}/planning/amend")
def amend_agent_plan(run_id: str, request: PlanningSubmitRequest) -> dict[str, Any]:
    return _submit_plan(run_id, request, amend=True)


@router.post("/{run_id}/planning/check")
def check_agent_plan(run_id: str) -> dict[str, Any]:
    service = default_agent_run_service()
    snapshot = _load(service, run_id)
    mode = planning_mode()
    with unit_of_work(service.database) as work:
        runs = PostgresAgentRunRepository(work.connection, service.context)
        planning = PostgresPlanningRepository(work.connection, service.context)
        revision = _current_revision(service, runs, run_id)
        state = planning.get_state(run_id)
        evidence = planning.list_inspection_evidence(run_id, task_revision_id=revision.revision_id)
        candidates = planning.list_impact_candidates(run_id, task_revision_id=revision.revision_id)
        plan = planning.latest_approved_plan(run_id, task_revision_id=revision.revision_id)
        digest = inspection_evidence_digest(evidence)
        guidance_digest = _repository_guidance_digest(snapshot, revision, plan)
        failures = _plan_freshness_failures(plan, revision, digest, guidance_digest)
        if plan is not None:
            failures.extend(plan_conformance_failures(snapshot.spec, plan, candidates))
        if state is None:
            failures.append("planning_state_missing")
        else:
            if state.get("task_revision_id") != revision.revision_id:
                failures.append("planning_state_task_revision_stale")
            if str(state.get("status") or "") != "approved":
                failures.append(f"latest_plan_state_not_approved:{state.get('status')}")
            active_id = str(state.get("active_plan_revision_id") or "") or None
            if plan is not None and active_id != plan.plan_revision_id:
                failures.append("planning_active_plan_identity_mismatch")
        work.rollback()
    failures = list(dict.fromkeys(failures))
    return {
        "mode": mode,
        "passed": not failures,
        "would_block": bool(failures),
        "plan_revision_id": plan.plan_revision_id if plan else None,
        "failures": failures,
    }


@router.post("/{run_id}/planning/authorize")
def authorize_agent_planned_operation(
    run_id: str,
    request: PlanningAuthorizeRequest,
) -> dict[str, Any]:
    service = default_agent_run_service()
    snapshot = _load(service, run_id)
    mode = planning_mode()
    command = str(request.command or request.input.get("command") or "")
    target = str(request.path or request.input.get("path") or "").strip() or None
    # Effect is always server-derived from the actual tool + command. A caller
    # may not relabel a mutating command as validation to bypass plan authority.
    effect = classify_operation_effect(request.tool_name, command=command)

    if mode == "off":
        return {
            "allowed": True,
            "would_block": False,
            "mode": mode,
            "effect": effect,
            "reasons": [],
        }

    with unit_of_work(service.database) as work:
        runs = PostgresAgentRunRepository(work.connection, service.context)
        quality = PostgresCodingQualityRepository(work.connection, service.context)
        planning = PostgresPlanningRepository(work.connection, service.context)
        revision = _current_revision(service, runs, run_id)
        state = planning.get_state(run_id)
        evidence = planning.list_inspection_evidence(run_id, task_revision_id=revision.revision_id)
        candidates = planning.list_impact_candidates(run_id, task_revision_id=revision.revision_id)
        plan = planning.latest_approved_plan(run_id, task_revision_id=revision.revision_id)

        # The plan is an authority boundary for mutation, not a prerequisite for
        # inspection or validation. Those operations remain usable to gather
        # evidence and diagnose failures before a plan or PlanDelta exists.
        if effect in {"read", "validate"}:
            reasons: list[str] = []
        else:
            guidance_digest = _repository_guidance_digest(snapshot, revision, plan)
            reasons = operation_plan_failures(
                plan,
                revision,
                effect=effect,
                target_path=target,
                command=command,
                current_evidence_digest=inspection_evidence_digest(evidence),
                quality_stage=quality.get_stage(run_id),
            )
            reasons.extend(
                item for item in _plan_freshness_failures(
                    plan,
                    revision,
                    inspection_evidence_digest(evidence),
                    guidance_digest,
                )
                if item not in reasons
            )
            if state is None:
                reasons.append("planning_state_missing")
            else:
                if state.get("task_revision_id") != revision.revision_id:
                    reasons.append("planning_state_task_revision_stale")
                if str(state.get("status") or "") in {"rejected", "stale", "invalid", "required", "submitted"}:
                    reasons.append(f"latest_plan_state_not_approved:{state.get('status')}")
                active_id = str(state.get("active_plan_revision_id") or "") or None
                if plan is not None and active_id != plan.plan_revision_id:
                    reasons.append("planning_active_plan_identity_mismatch")
            if effect == "unknown" and command and not _unknown_command_is_explicitly_planned(plan, command):
                reasons.append("unknown_command_requires_explicit_plan_hint")
            if effect in {"mutate", "unknown"} and plan is not None:
                # Before a mutation, only enforce drift/scope parts of
                # conformance; planned MODIFY items are not expected complete.
                drift = plan_conformance_failures(snapshot.spec, plan, candidates)
                reasons.extend(
                    item for item in drift
                    if item.startswith("unplanned_modified_path:")
                    or item.startswith("preexisting_dirty_path_modified:")
                    or item == "planning_base_commit_changed"
                )

        reasons = list(dict.fromkeys(reasons))
        would_block = bool(reasons)
        allowed = not would_block or mode == "shadow"
        if would_block and plan is not None and _planning_state_should_stale(reasons):
            planning.mark_state_stale(run_id)
        decision = PlanningDecision(
            run_id=run_id,
            task_revision_id=revision.revision_id,
            plan_revision_id=plan.plan_revision_id if plan else None,
            mode=mode,
            tool_name=request.tool_name,
            effect=effect,
            target=target or (command[:500] if command else None),
            allowed=allowed,
            would_block=would_block,
            reasons=reasons,
        )
        planning.add_decision(decision)
        work.commit()

    return {
        "allowed": allowed,
        "would_block": would_block,
        "mode": mode,
        "effect": effect,
        "plan_revision_id": plan.plan_revision_id if plan else None,
        "reasons": reasons,
        "reason": (
            "Omnix planning authority blocked this operation: " + ", ".join(reasons)
            if not allowed else None
        ),
    }
