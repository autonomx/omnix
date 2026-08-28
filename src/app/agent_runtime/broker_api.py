"""Run-scoped PostgreSQL-authoritative broker for external agent capabilities."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent_runtime.capabilities import default_capability_registry
from app.assistant_tools.gate import review_assistant_tool_request
from app.assistant_tools.hermes_bridge import hermes_assistant_tool_execute_payload
from app.assistant_tools.models import AssistantToolRequest, AssistantToolResult
from app.persistence.unit_of_work import unit_of_work

from .budget import AgentBudgetError, default_agent_budget_manager
from .contracts import AgentApproval, AgentEvent
from .evidence import build_evidence_receipt, is_evidence_capability
from .repository import PostgresAgentRunRepository
from .service import default_agent_run_service

router = APIRouter(prefix="/api/agent-runs", tags=["agent-runtime"])


class BrokerToolBudgetRequest(BaseModel):
    tool_name: str


class BrokerToolBudgetResponse(BaseModel):
    allowed: bool = True
    usage: dict[str, Any] = Field(default_factory=dict)


class BrokerCapabilityRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    proposal_id: str | None = None
    approval_id: str | None = None


class BrokerCapabilityResponse(BaseModel):
    capability_id: str
    executed: bool = False
    approval_required: bool = False
    approval_id: str | None = None
    execution_key: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)


def _execution_key(run_id: str, capability_id: str, request: BrokerCapabilityRequest) -> str:
    if request.proposal_id:
        raw = str(request.proposal_id).strip()
    else:
        payload = json.dumps(
            {"capability_id": capability_id, "input": request.input},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        raw = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"agent:{run_id}:{raw}"


def _approved_execution_key(
    run_id: str,
    canonical: str,
    request: BrokerCapabilityRequest,
    approval: AgentApproval,
) -> str:
    if approval.capability_id != canonical:
        raise HTTPException(status_code=403, detail="agent_approval_mismatch")
    approved_input = approval.request_payload.get("input")
    if not isinstance(approved_input, dict) or approved_input != request.input:
        raise HTTPException(status_code=403, detail="agent_approval_input_mismatch")
    execution_key = str(approval.request_payload.get("execution_key") or "").strip()
    if not execution_key or not execution_key.startswith(f"agent:{run_id}:"):
        raise HTTPException(status_code=409, detail="agent_approval_execution_identity_invalid")
    return execution_key


def _scope_candidate_values(
    resource_type: str,
    payload: dict[str, Any],
) -> list[object]:
    resource = str(resource_type or "").strip().casefold()
    aliases: dict[str, tuple[str, ...]] = {
        "repository": ("repository", "repo"),
        "repo": ("repository", "repo"),
        "device": ("device_id", "target", "id"),
        "target": ("target", "id"),
        "message": ("message_id", "id"),
        "thread": ("thread_id", "id"),
        "event": ("event_id", "id"),
        "recipient": ("recipient", "to", "email"),
        "contact": ("contact_id", "email", "id"),
        "account": ("account_id", "id"),
        "branch": ("branch",),
        "pull_request": ("number", "pull_request_id", "id"),
    }
    keys = list(
        dict.fromkeys(
            (
                resource,
                f"{resource}_id" if resource else "",
                "resource_id",
                *aliases.get(resource, ()),
            )
        )
    )
    values: list[object] = []
    for key in keys:
        if not key or key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, list):
            values.extend(value)
        else:
            values.append(value)
    return values


def _constraint_matches(actual: object, expected: object) -> bool:
    if isinstance(expected, list):
        return any(_constraint_matches(actual, item) for item in expected)
    if isinstance(actual, list):
        return any(_constraint_matches(item, expected) for item in actual)
    if isinstance(expected, str):
        return str(actual or "").strip().casefold() == expected.strip().casefold()
    return actual == expected


def _request_within_resource_scopes(
    snapshot,
    capability_id: str,
    payload: dict[str, Any],
) -> bool:
    registry = default_capability_registry()
    scopes = [
        scope
        for scope in snapshot.spec.resource_scopes
        if registry.canonical_id(scope.capability) == capability_id
    ]
    if not scopes:
        return True
    for scope in scopes:
        if scope.resource_id != "*":
            candidates = _scope_candidate_values(scope.resource_type, payload)
            if not any(
                _constraint_matches(candidate, scope.resource_id)
                for candidate in candidates
            ):
                continue
        if not all(
            key in payload and _constraint_matches(payload.get(key), expected)
            for key, expected in scope.constraints.items()
        ):
            continue
        return True
    return False


def _evidence_requirement_for_capability(policy, capability_id: str):
    from .evidence import SOURCE_CAPABILITIES

    for requirement in policy.requirements:
        candidates = [requirement.source_class]
        if requirement.fallback_policy != "fail_closed":
            candidates.extend(option.source_class for option in requirement.acceptable_sources)
        for source_class in candidates:
            resolved = SOURCE_CAPABILITIES.get(source_class)
            if resolved and resolved[0] == capability_id:
                return requirement
    return None


def _bind_authoritative_capability_input(
    snapshot,
    capability_id: str,
    request: BrokerCapabilityRequest,
    *,
    policy=None,
) -> BrokerCapabilityRequest:
    bounded = dict(request.input)
    requirement = _evidence_requirement_for_capability(policy, capability_id) if policy is not None else None
    subject = requirement.subject if requirement is not None else None

    def bind_exact(key: str, value: object) -> None:
        if value in {None, ""}:
            return
        if key in bounded and str(bounded.get(key)).casefold() != str(value).casefold():
            raise HTTPException(
                status_code=403,
                detail=f"agent_evidence_subject_input_mismatch:{key}",
            )
        bounded[key] = value

    if capability_id == "trading.market_quote" and subject is not None:
        bind_exact("ticker", subject.qualifiers.get("ticker"))
    elif capability_id in {"github.inspect_ci", "github.read_repo"} and subject is not None:
        bind_exact("repository", subject.canonical_id)
        requested_ref = subject.qualifiers.get("requested_ref")
        resolved_commit = subject.qualifiers.get("resolved_commit")
        bind_exact("requested_ref", requested_ref)
        if resolved_commit:
            if "sha" in bounded and str(bounded.get("sha")).casefold() != str(resolved_commit).casefold():
                raise HTTPException(
                    status_code=403,
                    detail="agent_evidence_subject_input_mismatch:sha",
                )
            bind_exact("ref", resolved_commit)
            bounded["resolved_commit"] = resolved_commit

    if capability_id == "github.push":
        workspace = snapshot.spec.workspace
        if workspace is None:
            raise HTTPException(
                status_code=409,
                detail="agent_push_requires_issued_workspace",
            )
        if "worktree" in bounded:
            raise HTTPException(
                status_code=403,
                detail="agent_push_worktree_is_omnix_managed",
            )
        if "remote" in bounded:
            raise HTTPException(
                status_code=403,
                detail="agent_push_remote_is_omnix_managed",
            )
        issued_worktree = workspace.worktree or workspace.root
        bounded.update({
            "worktree": issued_worktree,
            "remote": "origin",
        })
    return request.model_copy(update={"input": bounded})

def _effective_evidence_context(service, snapshot):
    with unit_of_work(service.database) as work:
        repository = PostgresAgentRunRepository(work.connection, service.context)
        latest_revision = repository.latest_task_revision(snapshot.run_id)
        receipts = repository.list_evidence_receipts(snapshot.run_id)
        work.rollback()
    policy = (
        latest_revision.evidence_decision.policy
        if latest_revision is not None
        else snapshot.spec.evidence_policy
    )
    revision_id = latest_revision.revision_id if latest_revision is not None else None
    started_at = latest_revision.created_at if latest_revision is not None else snapshot.created_at
    return policy, revision_id, started_at, receipts


def _reserve_evidence_retrieval_budget(
    repository: PostgresAgentRunRepository,
    run_id: str,
    capability_id: str,
    execution_key: str,
    request: BrokerCapabilityRequest,
    *,
    policy,
    revision_id: str | None,
    started_at,
) -> BrokerCapabilityRequest:
    if not is_evidence_capability(capability_id):
        return request
    if not revision_id:
        raise HTTPException(
            status_code=409,
            detail="agent_evidence_task_revision_unavailable",
        )
    retrieval = policy.retrieval
    now = datetime.now(timezone.utc)
    if started_at is not None:
        age = (now - started_at.astimezone(timezone.utc)).total_seconds()
        if age > retrieval.max_wall_time_seconds:
            raise HTTPException(
                status_code=429,
                detail="agent_evidence_retrieval_wall_time_exceeded",
            )

    bounded = dict(request.input)
    if capability_id == "research.web_search":
        try:
            requested_sources = int(bounded.get("max_results", 5))
        except (TypeError, ValueError):
            requested_sources = 5
        try:
            requested_extracts = int(bounded.get("max_extracts", retrieval.max_extracts))
        except (TypeError, ValueError):
            requested_extracts = retrieval.max_extracts
        requested_sources = max(1, min(requested_sources, 10))
        requested_extracts = max(0, min(requested_extracts, 4))
    else:
        requested_sources = 1
        requested_extracts = 0

    reservation = repository.reserve_evidence_query(
        run_id,
        revision_id,
        execution_key,
        max_queries=retrieval.max_queries,
        max_sources=retrieval.max_sources,
        max_extracts=retrieval.max_extracts,
        requested_sources=requested_sources,
        requested_extracts=requested_extracts,
    )
    if not reservation.get("allowed"):
        reason = str(reservation.get("reason") or "query_budget_exceeded")
        detail = {
            "query_budget_exceeded": "agent_evidence_retrieval_query_budget_exceeded",
            "source_budget_exceeded": "agent_evidence_retrieval_source_budget_exceeded",
        }.get(reason, "agent_evidence_retrieval_budget_exceeded")
        raise HTTPException(status_code=429, detail=detail)

    if capability_id == "research.web_search":
        bounded["max_results"] = int(reservation["reserved_sources"])
        bounded["max_extracts"] = int(reservation["reserved_extracts"])
    return request.model_copy(update={"input": bounded})


def _evidence_result_usage(result_payload: dict[str, Any], *, failed: bool) -> tuple[int, int]:
    if failed:
        return 0, 0
    output = result_payload.get("output")
    output = dict(output) if isinstance(output, dict) else {}
    diagnostics = output.get("diagnostics")
    diagnostics = dict(diagnostics) if isinstance(diagnostics, dict) else {}
    items = output.get("items")
    source_count = diagnostics.get("source_count", output.get("source_count"))
    try:
        sources = int(source_count)
    except (TypeError, ValueError):
        sources = len(items) if isinstance(items, list) else 1
    try:
        extracts = int(diagnostics.get("extracted_pages", 0))
    except (TypeError, ValueError):
        extracts = 0
    return max(0, sources), max(0, extracts)


def _review_with_run_policy(
    request: AssistantToolRequest,
    run_policy: str,
):
    """Apply run policy as an approval floor, never as a weakening override."""
    base_request = request.model_copy(update={"approval_policy": None})
    base = review_assistant_tool_request(base_request)
    if not base.allowed or run_policy == "allow_automatic":
        return base_request, base
    if run_policy == "disabled":
        disabled_request = request.model_copy(update={"approval_policy": "disabled"})
        return disabled_request, review_assistant_tool_request(disabled_request)
    # If the canonical tool/action/config already requires approval, preserve
    # that stronger decision rather than replacing it with a weaker run policy.
    if base.approval_required:
        return base_request, base
    overlay_request = request.model_copy(update={"approval_policy": run_policy})
    overlay = review_assistant_tool_request(overlay_request)
    return overlay_request, overlay


def _validate_execution_input(
    request: BrokerCapabilityRequest,
    stored: dict[str, Any],
) -> None:
    request_payload = stored.get("request_payload")
    stored_input = (
        request_payload.get("input")
        if isinstance(request_payload, dict)
        else None
    )
    if not isinstance(stored_input, dict) or stored_input != request.input:
        raise HTTPException(
            status_code=409,
            detail="agent_execution_key_input_mismatch",
        )


def _stored_response(
    capability_id: str,
    execution_key: str,
    stored: dict[str, Any],
) -> BrokerCapabilityResponse:
    result = dict(stored.get("result_payload") or {})
    return BrokerCapabilityResponse(
        capability_id=capability_id,
        execution_key=execution_key,
        executed=stored.get("state") == "completed" and not stored.get("error"),
        result=result,
    )


@router.post(
    "/{run_id}/budget/tool",
    response_model=BrokerToolBudgetResponse,
)
def authorize_agent_tool_call(
    run_id: str,
    request: BrokerToolBudgetRequest,
) -> BrokerToolBudgetResponse:
    try:
        usage = default_agent_budget_manager().authorize_tool_call(
            run_id,
            tool_name=request.tool_name,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent_run_not_found") from exc
    except AgentBudgetError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return BrokerToolBudgetResponse(usage=dict(usage))


@router.post("/{run_id}/capabilities/{capability_id:path}", response_model=BrokerCapabilityResponse)
def execute_agent_capability(
    run_id: str,
    capability_id: str,
    request: BrokerCapabilityRequest,
) -> BrokerCapabilityResponse:
    service = default_agent_run_service()
    snapshot = service.get(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")
    if snapshot.status not in {"starting", "running", "waiting_for_approval"}:
        raise HTTPException(
            status_code=409,
            detail=f"agent_run_not_runnable:{snapshot.status}",
        )
    if snapshot.desired_state != "running":
        raise HTTPException(
            status_code=409,
            detail=f"agent_run_not_runnable:{snapshot.desired_state}",
        )
    capability = default_capability_registry().get(capability_id)
    if capability is None or capability.execution_zone != "broker":
        raise HTTPException(status_code=404, detail="agent_capability_not_found")
    canonical = capability.id
    if canonical not in snapshot.spec.external_capabilities:
        raise HTTPException(status_code=403, detail="agent_capability_outside_run_spec")
    policy, task_revision_id, evidence_started_at, existing_receipts = _effective_evidence_context(
        service,
        snapshot,
    )
    request = _bind_authoritative_capability_input(
        snapshot,
        canonical,
        request,
        policy=policy,
    )
    if not _request_within_resource_scopes(snapshot, canonical, request.input):
        raise HTTPException(status_code=403, detail="agent_resource_scope_mismatch")

    execution_key = _execution_key(run_id, canonical, request)
    approved = False
    approval = None

    with unit_of_work(service.database) as work:
        repository = PostgresAgentRunRepository(work.connection, service.context)
        request = _reserve_evidence_retrieval_budget(
            repository,
            run_id,
            canonical,
            execution_key,
            request,
            policy=policy,
            revision_id=task_revision_id,
            started_at=evidence_started_at,
        )
        if request.approval_id:
            approval = repository.get_approval(run_id, request.approval_id)
            if approval is None:
                raise HTTPException(status_code=403, detail="agent_approval_mismatch")
            execution_key = _approved_execution_key(
                run_id,
                canonical,
                request,
                approval,
            )
            approved = approval.state == "approved"

        stored = repository.ensure_capability_execution(
            run_id,
            execution_key,
            canonical,
            {"input": request.input, "approval_id": request.approval_id},
        )
        if stored["capability_id"] != canonical:
            raise HTTPException(status_code=409, detail="agent_execution_key_capability_mismatch")
        _validate_execution_input(request, stored)
        if stored["state"] in {"completed", "failed"}:
            work.rollback()
            return _stored_response(canonical, execution_key, stored)
        if stored["state"] == "running":
            reclaimed = False
            if capability.effect == "read":
                try:
                    retry_after = max(
                        1,
                        int(os.environ.get("OMNIX_AGENT_READ_RETRY_AFTER_SECONDS", "30")),
                    )
                except ValueError:
                    retry_after = 30
                reclaimed = repository.reclaim_stale_read_capability_execution(
                    run_id,
                    execution_key,
                    stale_before=datetime.now(timezone.utc) - timedelta(seconds=retry_after),
                )
                if reclaimed:
                    stored = repository.ensure_capability_execution(
                        run_id,
                        execution_key,
                        canonical,
                        {"input": request.input, "approval_id": request.approval_id},
                    )
            if not reclaimed:
                work.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="agent_execution_outcome_unknown_or_in_progress",
                )

        if approval is not None and approval.state == "rejected":
            repository.finish_capability_execution(
                run_id,
                execution_key,
                result_payload={"error": "approval_rejected"},
                error="approval_rejected",
                state_changed=False,
            )
            work.commit()
            return BrokerCapabilityResponse(
                capability_id=canonical,
                execution_key=execution_key,
                result={"error": "approval_rejected"},
            )

        if approval is None and stored["state"] == "waiting_for_approval":
            approval = repository.find_capability_approval(
                run_id,
                canonical,
                execution_key,
            )
            if approval is not None:
                execution_key = _approved_execution_key(
                    run_id,
                    canonical,
                    request,
                    approval,
                )
                approved = approval.state == "approved"

        tool_request = AssistantToolRequest(
            tool_id=canonical.split(".", 1)[0],
            action_id=canonical,
            session_id=snapshot.spec.session_id or f"agent:{run_id}",
            proposal_id=execution_key,
            input=request.input,
            approved=approved,
        )
        tool_request, decision = _review_with_run_policy(
            tool_request,
            snapshot.spec.approval_policy,
        )
        if not decision.allowed:
            repository.finish_capability_execution(
                run_id,
                execution_key,
                result_payload={"error": decision.reason or "not_allowed"},
                error=decision.reason or "not_allowed",
                state_changed=False,
            )
            work.commit()
            return BrokerCapabilityResponse(
                capability_id=canonical,
                execution_key=execution_key,
                result={"error": decision.reason or "not_allowed"},
            )
        if decision.approval_required and not approved:
            repository.mark_capability_waiting_for_approval(run_id, execution_key)
            if approval is None:
                approval = AgentApproval(
                    run_id=run_id,
                    capability_id=canonical,
                    request_payload={
                        "input": request.input,
                        "proposal_id": execution_key,
                        "execution_key": execution_key,
                    },
                )
                repository.add_approval(approval)
                current = repository.get_run(run_id)
                if current is not None and current.status != "waiting_for_approval":
                    repository.update_state(
                        run_id,
                        expected_revision=current.revision,
                        status="waiting_for_approval",
                    )
            work.commit()
            return BrokerCapabilityResponse(
                capability_id=canonical,
                approval_required=True,
                approval_id=approval.approval_id,
                execution_key=execution_key,
            )
        if not repository.claim_capability_execution(run_id, execution_key):
            work.rollback()
            raise HTTPException(status_code=409, detail="agent_execution_not_claimable")
        work.commit()

    payload = hermes_assistant_tool_execute_payload(
        f"agent:{run_id}",
        tool_request.model_copy(update={"approved": approved or not decision.approval_required}),
    )
    result: AssistantToolResult = payload.execution_result
    result_payload = result.model_dump(mode="json")

    with unit_of_work(service.database) as work:
        repository = PostgresAgentRunRepository(work.connection, service.context)
        repository.finish_capability_execution(
            run_id,
            execution_key,
            result_payload=result_payload,
            error=result.error,
            state_changed=result.state_changed,
        )
        if task_revision_id and is_evidence_capability(canonical):
            actual_sources, actual_extracts = _evidence_result_usage(
                result_payload,
                failed=result.error is not None,
            )
            repository.finish_evidence_query(
                run_id,
                task_revision_id,
                execution_key,
                actual_sources=actual_sources,
                actual_extracts=actual_extracts,
                failed=result.error is not None,
            )
        receipt = build_evidence_receipt(
            run_id=run_id,
            task_revision_id=task_revision_id,
            policy=policy,
            capability_id=canonical,
            request_input=request.input,
            result_payload=result_payload,
            error=result.error,
        )
        if receipt is not None:
            repository.add_evidence_receipt(receipt)
        repository.append_event(
            AgentEvent(
                run_id=run_id,
                event_type="tool.completed",
                payload={
                    "capability_id": canonical,
                    "execution_key": execution_key,
                    "broker": True,
                    "state_changed": result.state_changed,
                    "error": result.error,
                    "result_summary": result.result_summary,
                },
            )
        )
        work.commit()

    return BrokerCapabilityResponse(
        capability_id=canonical,
        execution_key=execution_key,
        executed=result.error is None,
        approval_required=False,
        approval_id=request.approval_id,
        result=result_payload,
    )
