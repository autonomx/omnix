"""Durable public proposal, decision and single-use execution flow."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field

from app.persistence.capability_approval_repository import (
    CapabilityApprovalConflict, CapabilityProposal, PostgresCapabilityApprovalRepository,
)
from app.persistence.database import PostgresDatabase, default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work

from .gate import review_assistant_tool_request
from .hermes_bridge import _run_assistant_tool_request
from .hermes_payloads import HermesAssistantToolExecutePayload
from .ledger import AssistantToolLedgerEntry, summarize_tool_input
from .models import AssistantToolRequest, AssistantToolResult
from .result_context import tool_result_to_chat_context


class AssistantToolProposalPayload(BaseModel):
    proposal_id: str
    approval_required: bool
    decision: str
    expires_at: datetime
    request: AssistantToolRequest


class AssistantToolProposalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=2000)


class ToolProposalNotAllowed(PermissionError):
    pass


def _canonical(request: AssistantToolRequest) -> dict:
    return {
        "capability_id": request.action_id.strip(), "action": request.action_id.strip(),
        "tool_id": request.tool_id.strip(), "input": request.input, "session": request.session_id,
    }


def _request(proposal: CapabilityProposal) -> AssistantToolRequest:
    data = proposal.payload
    return AssistantToolRequest(
        tool_id=data["tool_id"], action_id=data["action"], input=data["input"],
        session_id=data["session"], proposal_id=proposal.id,
    )


def _response(proposal: CapabilityProposal) -> AssistantToolProposalPayload:
    return AssistantToolProposalPayload(
        proposal_id=proposal.id, approval_required=proposal.approval_required,
        decision=proposal.decision, expires_at=proposal.expires_at, request=_request(proposal),
    )


class AssistantToolProposalService:
    def __init__(self, database: PostgresDatabase, context: TenantContext) -> None:
        self.database = database
        self.context = context

    def propose(self, request: AssistantToolRequest) -> AssistantToolProposalPayload:
        decision = review_assistant_tool_request(request)
        if not decision.allowed:
            raise ToolProposalNotAllowed(decision.reason or "tool_not_allowed")
        with unit_of_work(self.database) as work:
            proposal = PostgresCapabilityApprovalRepository(work.connection).create(
                self.context, capability_id=request.action_id.strip(), payload=_canonical(request),
                approval_required=decision.approval_required,
            )
            work.commit()
        return _response(proposal)

    def decide(self, identifier: str, *, approve: bool, reason: str | None = None) -> AssistantToolProposalPayload:
        with unit_of_work(self.database) as work:
            proposal = PostgresCapabilityApprovalRepository(work.connection).decide(
                self.context, identifier, approve=approve, reason=reason,
            )
            work.commit()
        return _response(proposal)

    def execute(
        self, identifier: str, *, expected_request: AssistantToolRequest | None = None,
        user_request: str = "",
    ) -> HermesAssistantToolExecutePayload:
        with unit_of_work(self.database) as work:
            repository = PostgresCapabilityApprovalRepository(work.connection)
            proposal = repository.get(self.context, identifier, lock=True)
            if proposal is None:
                raise KeyError(identifier)
            if proposal.decision not in {"pending", "approved"}:
                raise CapabilityApprovalConflict("proposal_denied_expired_or_consumed")
            request = _request(proposal)
            # Recheck current configuration: an old proposal cannot preserve a
            # weaker policy after the operator disables or restricts an action.
            decision = review_assistant_tool_request(request, approved=proposal.decision == "approved")
            if not decision.allowed or not decision.executable:
                raise ToolProposalNotAllowed(decision.reason or "approval_required")
            entry = AssistantToolLedgerEntry(
                proposal_id=identifier, session_id=request.session_id, tool_id=request.tool_id,
                action_id=request.action_id, approval_source="user" if proposal.decision == "approved" else "policy",
                input_summary=summarize_tool_input(request.input), error="execution_reserved",
            )
            repository.consume(
                self.context, identifier, expected_payload=_canonical(expected_request or request),
                ledger_payload=entry.model_dump(mode="json"),
            )
            work.commit()
        # The reservation is durable before an external action starts. Failure
        # or a process crash must never make this proposal executable again.
        try:
            result = _run_assistant_tool_request(request, decision.risk_level)
        except Exception:
            result = AssistantToolResult(
                tool_id=request.tool_id, action_id=request.action_id, session_id=request.session_id,
                risk_level=decision.risk_level, error="tool_execution_failed", result_summary="Tool execution failed.",
            )
        entry = entry.model_copy(update={
            "error": result.error, "state_changed": result.state_changed, "result_summary": result.result_summary,
        })
        with unit_of_work(self.database) as work:
            cursor = work.connection.execute(
                """UPDATE omnix_module_records SET payload = %s::jsonb,
                          revision = revision + 1, updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND module = 'assistant-tools'
                       AND record_type = 'execution-ledger' AND record_id = %s
                       AND payload->>'proposal_id' = %s
                       AND payload->>'error' = 'execution_reserved'""",
                (entry.model_dump_json(), self.context.workspace_id, entry.execution_id, identifier),
            )
            if cursor.rowcount != 1:
                raise CapabilityApprovalConflict("execution_ledger_reservation_lost")
            work.commit()
        return HermesAssistantToolExecutePayload(
            user_request=user_request, selected_tool_id=request.tool_id, selected_action_id=request.action_id,
            approval_decision=decision, execution_result=result,
            result_context=tool_result_to_chat_context(result, entry), state_changed=result.state_changed,
        )


@lru_cache(maxsize=1)
def default_tool_proposal_service() -> AssistantToolProposalService:
    database = default_database()
    return AssistantToolProposalService(database, bootstrap_local_tenant(database))
