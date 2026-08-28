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


_AGENT = re.compile(r"^(?:/agent\b|/agnet\b|agent[,:]\s|use (?:the )?agent\b)", re.I)
_WORKFLOW = re.compile(r"^(?:run|start|execute)\s+(?:my\s+)?(.+?)(?:\s+routine|\s+workflow)?[.!]?$", re.I)
_CASUAL = re.compile(r"^(?:hi|hello|hey|thanks|thank you|how are you|what'?s up)[.!?\s]*$", re.I)
_INFORMATIONAL = re.compile(r"^(?:what|why|when|where|who|how|explain|describe|summarize|compare|teach me)\b", re.I)
_META_INFORMATIONAL = re.compile(
    r"^(?:what\s+(?:does|would|happens?)|why\s+would|how\s+(?:do|does|would)|"
    r"explain|describe|teach me)\b",
    re.I,
)
_HYPOTHETICAL = re.compile(
    r"^(?:if\s+i\s+asked|suppose\b|imagine\b|what\s+would\s+happen\s+if|"
    r"how\s+would\s+(?:an?|the)\s+agent|could\s+(?:an?|the)\s+agent)\b",
    re.I,
)
_NEGATED_ACTION = re.compile(
    r"(?:^(?:don'?t|do\s+not|never|no\s+need\s+to)\b|"
    r"\bi\s+(?:don'?t|do\s+not)\s+want\s+(?:you|the\s+agent)\s+to\b)",
    re.I,
)
_QUOTED_SPAN = re.compile(
    r'"[^"\\r\\n]*"'
    r"|“[^”\\r\\n]*”"
    r"|‘[^’\\r\\n]*’"
    r"|\`[^\`\\r\\n]*\`"
    r"|(?<!\\w)'[^'\\r\\n]+'(?!\\w)"
)

_BROAD_SEMANTIC = re.compile(r"\b(?:take care of|anything important|whatever needs|prepare everything|handle everything)\b", re.I)
_AGENTIC = re.compile(r"\b(?:fix|debugg?|investigate|figure out|diagnose|research|reseach|analy[sz]e|anlyze|refactor|implement)\b", re.I)
_RESEARCH_ACTION = re.compile(r"\b(?:research|reseach|investigate|analy[sz]e|anlyze)\b", re.I)
_HOME_SEMANTIC_TASK = re.compile(
    r"(?:\b(?:turn|set|adjust|lower|raise|check|inspect|prepare)\b.{0,100}"
    r"\b(?:thermostat|home|lights?|lamps?|plugs?|outlets?|kasa)\b|"
    r"\b(?:thermostat|home|lights?|lamps?|plugs?|outlets?|kasa)\b.{0,100}"
    r"\b(?:down|up|to|check|inspect|prepare)\b)",
    re.I,
)
_PERSONAL_TASK = re.compile(
    r"\b(?:chec?k|inspect|summarize|find|draft|send|schedule|create|look\s+up|resolve)\b"
    r".{0,100}\b(?:gmail|emails?|calendar|meetings?|contacts?|appointments?|schedule)\b",
    re.I,
)
_CONJUNCTION = re.compile(r"\b(?:and|then|also)\b", re.I)
_CONVERSATIONAL_SECOND_INTENT = re.compile(r"\b(?:tell me a joke|explain it|summarize it|answer me)\b", re.I)
_TRADING_SUBJECT = re.compile(
    r"\b(?:stocks?|trading|trades?|tickers?|markets?|shares?|equities|nvda|gme|tsla|"
    r"gainers?|losers?|orders?|positions?)\b",
    re.I,
)
_TRADING_MUTATION = re.compile(
    r"\b(?:buy|sell|purchase|short|cover)\b|"
    r"\b(?:place|submit|cancel)\b.{0,60}\b(?:order|trade|position)\b",
    re.I,
)

_DIRECT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bturn\s+on\b.*\b(?:plug|outlet|kasa|lamp|light)\b", re.I), "home.set_state"),
    (re.compile(r"\bturn\s+of{1,2}\b.*\b(?:plug|outlet|kasa|lamp|light)\b", re.I), "home.set_state"),
    (re.compile(r"\b(?:status|state)\b.*\b(?:plug|outlet|kasa|lamp|light)\b", re.I), "home.get_state"),
)


def route_omnix_request(
    content: str,
    *,
    workflow_lookup: Callable[[str], str | None] | None = None,
    research_mode: str | None = None,
) -> OmnixRouteDecision:
    text = " ".join(str(content or "").strip().split())
    if not text or _CASUAL.match(text):
        return OmnixRouteDecision(lane="chat", confidence=0.99, reason="casual_or_empty")
    if _AGENT.search(text):
        return OmnixRouteDecision(lane="agent", confidence=1.0, reason="explicit_agent", explicit=True)
    actionable_text = _QUOTED_SPAN.sub(" ", text)
    actionable_text = " ".join(actionable_text.split())
    if _HYPOTHETICAL.match(text):
        return OmnixRouteDecision(lane="chat", confidence=0.98, reason="hypothetical_or_conditional")
    if _NEGATED_ACTION.search(actionable_text):
        return OmnixRouteDecision(lane="chat", confidence=0.99, reason="negated_action")
    if _META_INFORMATIONAL.match(text):
        return OmnixRouteDecision(lane="chat", confidence=0.97, reason="informational")
    if _is_mixed_intent(actionable_text):
        return OmnixRouteDecision(
            lane="agent",
            confidence=0.82,
            reason="mixed_intent_task",
            hermes_recommended=True,
        )
    if _BROAD_SEMANTIC.search(text):
        return OmnixRouteDecision(
            lane="agent",
            confidence=0.72,
            reason="broad_semantic_task",
            hermes_recommended=True,
        )

    workflow_match = _WORKFLOW.match(actionable_text)
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
        if pattern.search(actionable_text):
            return OmnixRouteDecision(
                lane="direct",
                confidence=0.96,
                reason="known_single_capability",
                capability_id=capability_id,
            )

    if _INFORMATIONAL.match(text):
        return OmnixRouteDecision(lane="chat", confidence=0.95, reason="informational")
    normalized_research_mode = str(research_mode or "disabled").strip().casefold()
    if normalized_research_mode in {"quick", "deep"} and _RESEARCH_ACTION.search(actionable_text):
        return OmnixRouteDecision(
            lane="chat",
            confidence=0.99,
            reason=f"{normalized_research_mode}_research_chat",
        )
    if _HOME_SEMANTIC_TASK.search(actionable_text):
        return OmnixRouteDecision(lane="agent", confidence=0.84, reason="home_semantic_task")
    if _PERSONAL_TASK.search(actionable_text):
        return OmnixRouteDecision(lane="agent", confidence=0.84, reason="personal_assistant_task")
    if _AGENTIC.search(actionable_text):
        return OmnixRouteDecision(lane="agent", confidence=0.9, reason="open_ended_execution")
    return OmnixRouteDecision(
        lane="chat",
        confidence=0.7,
        reason="conversation_default",
        hermes_recommended=False,
    )


def _is_mixed_intent(text: str) -> bool:
    if _CONJUNCTION.search(text) is None:
        return False
    signals = 0
    if any(pattern.search(text) for pattern, _ in _DIRECT_PATTERNS):
        signals += 1
    if re.search(r"\b(?:run|start|execute)\b.{0,80}\b(?:routine|workflow)\b", text, re.I):
        signals += 1
    if _PERSONAL_TASK.search(text):
        signals += 1
    if _HOME_SEMANTIC_TASK.search(text):
        signals += 1
    if _AGENTIC.search(text):
        signals += 1
    if _TRADING_SUBJECT.search(text) and _RESEARCH_ACTION.search(text):
        signals += 1
    if _TRADING_MUTATION.search(text):
        signals += 1
    if _CONVERSATIONAL_SECOND_INTENT.search(text):
        signals += 1
    return signals >= 2
