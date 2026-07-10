"""Proposal-only Hermes planner used by automatically routed live voice turns."""
from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

from app.assistant_tools.hermes_bridge import hermes_assistant_tool_execute_payload
from app.assistant_tools.kasa_plan import KASA_READ_TOOLS, kasa_request_from_tool_call

from .core import AssistantRequest, ToolResult
from .hermes_client import HermesSidecarClient
from .hermes_status import hermes_runtime_config
from .mode_apply import apply_mode_result
from .mode_chat import ModeChatResponse, detect_mode_domain


class LiveAgentUnavailable(RuntimeError):
    pass


def plan_live_agent_proposal(
    *,
    content: str,
    session_id: str,
    context: dict[str, Any] | None = None,
    timeout_seconds: float = 6.0,
) -> ModeChatResponse:
    config = hermes_runtime_config()
    if not config.enabled:
        raise LiveAgentUnavailable("Hermes is disabled")
    request = AssistantRequest(
        message=content,
        session_id=session_id,
        domain=detect_mode_domain(content),
        dry_run=True,
        metadata={
            "source": "live_agent",
            "proposal_only": True,
            "review_required": True,
            "executes": False,
            **(context or {}),
        },
    )
    try:
        result = HermesSidecarClient(
            base_url=config.base_url,
            api_key=os.environ.get("HERMES_API_KEY") or None,
            timeout=min(config.timeout_seconds, timeout_seconds),
        ).plan(request)
    except Exception as exc:
        raise LiveAgentUnavailable(str(exc) or "Hermes planner is unavailable") from exc
    result = apply_mode_result(result, dry_run=True)
    _apply_kasa_reads(result, content=content, session_id=session_id)
    for row in result.tool_results:
        if row.name not in KASA_READ_TOOLS:
            row.executed = False
    result.requires_confirmation = any(
        call.name not in KASA_READ_TOOLS for call in result.tool_calls
    )
    return ModeChatResponse(
        ok=result.success,
        mode="agent",
        backend="hermes",
        result=asdict(result),
    )


def _apply_kasa_reads(result, *, content: str, session_id: str) -> None:
    rows = list(result.tool_results)
    for call in result.tool_calls:
        if call.name not in KASA_READ_TOOLS:
            continue
        request = kasa_request_from_tool_call(call, session_id=session_id, approved=False)
        if request is None:
            continue
        payload = hermes_assistant_tool_execute_payload(content, request)
        execution = payload.execution_result
        rows.append(
            ToolResult(
                name=call.name,
                ok=execution.error is None,
                output=execution.output,
                error=execution.error,
                executed=execution.error is None,
            )
        )
        if execution.result_summary:
            result.response = execution.result_summary
    if rows:
        result.tool_results = rows
        result.success = all(row.ok for row in rows)
