"""Run-scoped PostgreSQL-authoritative broker for external agent capabilities."""
from __future__ import annotations

import hashlib
import json
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
    capability = default_capability_registry().get(capability_id)
    if capability is None or capability.execution_zone != "broker":
        raise HTTPException(status_code=404, detail="agent_capability_not_found")
    canonical = capability.id
    if canonical not in snapshot.spec.external_capabilities:
        raise HTTPException(status_code=403, detail="agent_capability_outside_run_spec")

    execution_key = _execution_key(run_id, canonical, request)
    approved = False
    approval = None

    with unit_of_work(service.database) as work:
        repository = PostgresAgentRunRepository(work.connection, service.context)
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
        if stored["state"] in {"completed", "failed"}:
            work.rollback()
            return _stored_response(canonical, execution_key, stored)
        if stored["state"] == "running":
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
            approved = approval is not None and approval.state == "approved"

        tool_request = AssistantToolRequest(
            tool_id=canonical.split(".", 1)[0],
            action_id=canonical,
            session_id=snapshot.spec.session_id or f"agent:{run_id}",
            proposal_id=execution_key,
            input=request.input,
            approved=approved,
        )
        decision = review_assistant_tool_request(tool_request)
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
