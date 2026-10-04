"""How a TaskGraph capability node reaches the assistant tool executor (WP-8.2).

The one place the TaskGraph runtime depends on ``app.assistant_tools``.
"""
from __future__ import annotations

from typing import Any, Callable

from app.assistant_tools.models import AssistantToolRequest
from app.capabilities.executor import CapabilityGrant, execute_capability

# A capability node's executor: (session id, request) -> tool result.
CapabilityExecutor = Callable[[str, AssistantToolRequest], Any]


def default_capability_executor(session_id: str, request: AssistantToolRequest) -> Any:
    # Capability nodes are never pre-approved: the tool policy decides, and a
    # call that needs approval fails the node (WP-4.5).
    return execute_capability(CapabilityGrant("task_graph", session_id), request, user_request=session_id)


__all__ = ["AssistantToolRequest", "CapabilityExecutor", "default_capability_executor"]
