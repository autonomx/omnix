"""Proposal-only Hermes planner used by automatically routed live voice turns."""
from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

from .core import AssistantRequest
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
    for row in result.tool_results:
        row.executed = False
    result.requires_confirmation = True
    return ModeChatResponse(
        ok=result.success,
        mode="agent",
        backend="hermes",
        result=asdict(result),
    )
