"""Payload shells for Hermes assistant capability routes."""
from __future__ import annotations

from pydantic import BaseModel

from .models import AssistantToolRequest, AssistantToolResult, AssistantToolReviewDecision


class HermesAssistantToolReviewPayload(BaseModel):
    user_request: str = ""
    selected_tool_id: str
    selected_action_id: str
    tool_request: AssistantToolRequest
    approval_decision: AssistantToolReviewDecision


class HermesAssistantToolExecutePayload(BaseModel):
    user_request: str = ""
    selected_tool_id: str
    selected_action_id: str
    approval_decision: AssistantToolReviewDecision
    execution_result: AssistantToolResult
    state_changed: bool = False
