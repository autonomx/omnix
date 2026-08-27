"""Run-scoped broker for external agent capabilities."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent_runtime.capabilities import default_capability_registry
from app.assistant_tools.gate import review_assistant_tool_request
from app.assistant_tools.hermes_bridge import hermes_assistant_tool_execute_payload
from app.assistant_tools.models import AssistantToolRequest
from app.persistence.unit_of_work import unit_of_work
from .contracts import AgentApproval, AgentEvent
from .repository import PostgresAgentRunRepository
from .service import default_agent_run_service

router = APIRouter(prefix="/api/agent-runs", tags=["agent-runtime"])


class BrokerCapabilityRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    proposal_id: str | None = None
    approval_id: str | None = None


class BrokerCapabilityResponse(BaseModel):
    capability_id: str
    executed: bool = False
    approval_required: bool = False
    approval_id: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)


@router.post("/{run_id}/capabilities/{capability_id:path}", response_model=BrokerCapabilityResponse)
def execute_agent_capability(run_id: str, capability_id: str, request: BrokerCapabilityRequest) -> BrokerCapabilityResponse:
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

    approved, approval = False, None
    with unit_of_work(service.database) as work:
        repository = PostgresAgentRunRepository(work.connection, service.context)
        if request.approval_id:
            approval = repository.get_approval(run_id, request.approval_id)
            if approval is None or approval.capability_id != canonical:
                raise HTTPException(status_code=403, detail="agent_approval_mismatch")
            approved = approval.state == "approved"
        tool_request = AssistantToolRequest(
            tool_id=canonical.split(".", 1)[0], action_id=canonical,
            session_id=snapshot.spec.session_id or f"agent:{run_id}",
            proposal_id=request.proposal_id or f"agent:{run_id}:{canonical}",
            input=request.input, approved=approved,
        )
        decision = review_assistant_tool_request(tool_request)
        if decision.approval_required and not approved:
            if approval is None:
                approval = AgentApproval(run_id=run_id, capability_id=canonical, request_payload={"input": request.input, "proposal_id": tool_request.proposal_id})
                repository.add_approval(approval)
                current = repository.get_run(run_id)
                if current is not None and current.status != "waiting_for_approval":
                    repository.update_state(run_id, expected_revision=current.revision, status="waiting_for_approval")
                work.commit()
            else:
                work.rollback()
            return BrokerCapabilityResponse(capability_id=canonical, approval_required=True, approval_id=approval.approval_id)
        work.rollback()

    payload = hermes_assistant_tool_execute_payload(f"agent:{run_id}", tool_request.model_copy(update={"approved": approved or not decision.approval_required}))
    result = payload.execution_result
    with unit_of_work(service.database) as work:
        repository = PostgresAgentRunRepository(work.connection, service.context)
        repository.append_event(AgentEvent(run_id=run_id, event_type="tool.completed", payload={"capability_id": canonical, "broker": True, "state_changed": result.state_changed, "error": result.error, "result_summary": result.result_summary}))
        work.commit()
    return BrokerCapabilityResponse(capability_id=canonical, executed=result.error is None, approval_required=False, approval_id=request.approval_id, result=result.model_dump(mode="json"))
