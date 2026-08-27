"""Deterministic first-pass routing across Chat, Direct, Workflow, and Agent lanes."""
from __future__ import annotations

from collections.abc import Callable
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OmnixLane = Literal["chat", "direct", "workflow", "agent"]


class OmnixRouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lane: OmnixLane
    confidence: float = Field(ge=0, le=1)
    reason: str
    explicit: bool = False
    hermes_recommended: bool = False
    workflow_id: str | None = None
    capability_id: str | None = None


_AGENT = re.compile(r"^(?:/agent\b|agent[,:]\s|use (?:the )?agent\b)", re.I)
_WORKFLOW = re.compile(r"^(?:run|start|execute)\s+(?:my\s+)?(.+?)(?:\s+routine|\s+workflow)?[.!]?$", re.I)
_CASUAL = re.compile(r"^(?:hi|hello|hey|thanks|thank you|how are you|what'?s up)[.!?\s]*$", re.I)
_INFORMATIONAL = re.compile(r"^(?:what|why|when|where|who|how|explain|describe|summarize|compare|teach me)\b", re.I)
_BROAD_SEMANTIC = re.compile(r"\b(?:take care of|anything important|whatever needs|prepare everything|handle everything)\b", re.I)
_AGENTIC = re.compile(r"\b(?:fix|debug|investigate|figure out|diagnose|research|analy[sz]e|refactor|implement)\b", re.I)

_DIRECT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bturn\s+on\b.*\b(?:plug|outlet|kasa|lamp|light)\b", re.I), "home.set_state"),
    (re.compile(r"\bturn\s+off\b.*\b(?:plug|outlet|kasa|lamp|light)\b", re.I), "home.set_state"),
    (re.compile(r"\b(?:status|state)\b.*\b(?:plug|outlet|kasa|lamp|light)\b", re.I), "home.get_state"),
)


def route_omnix_request(
    content: str,
    *,
    workflow_lookup: Callable[[str], str | None] | None = None,
) -> OmnixRouteDecision:
    text = " ".join(str(content or "").strip().split())
    if not text or _CASUAL.match(text):
        return OmnixRouteDecision(lane="chat", confidence=0.99, reason="casual_or_empty")
    if _AGENT.search(text):
        return OmnixRouteDecision(lane="agent", confidence=1.0, reason="explicit_agent", explicit=True)
    if _BROAD_SEMANTIC.search(text):
        return OmnixRouteDecision(
            lane="agent",
            confidence=0.72,
            reason="broad_semantic_task",
            hermes_recommended=True,
        )

    workflow_match = _WORKFLOW.match(text)
    if workflow_match and workflow_lookup is not None:
        candidate = workflow_match.group(1).strip()
        workflow_id = workflow_lookup(candidate)
        if workflow_id:
            return OmnixRouteDecision(
                lane="workflow",
                confidence=0.98,
                reason="known_workflow",
                workflow_id=workflow_id,
            )

    for pattern, capability_id in _DIRECT_PATTERNS:
        if pattern.search(text):
            return OmnixRouteDecision(
                lane="direct",
                confidence=0.96,
                reason="known_single_capability",
                capability_id=capability_id,
            )

    if _INFORMATIONAL.match(text) and not _AGENTIC.search(text):
        return OmnixRouteDecision(lane="chat", confidence=0.95, reason="informational")
    if _AGENTIC.search(text):
        return OmnixRouteDecision(lane="agent", confidence=0.9, reason="open_ended_execution")
    return OmnixRouteDecision(
        lane="chat",
        confidence=0.7,
        reason="conversation_default",
        hermes_recommended=False,
    )
