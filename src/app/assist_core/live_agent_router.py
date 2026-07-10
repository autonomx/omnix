"""Deterministic, feature-gated routing between live chat and Live Agent."""
from __future__ import annotations

import os
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LiveAgentRequestedMode = Literal["off", "auto", "agent"]
LiveAgentRoute = Literal["direct_chat", "agent_plan"]

_EXPLICIT_AGENT = re.compile(
    r"^(?:/agent\b|agent[,:]\s|use (?:the )?agent\b|have (?:the )?agent\b)",
    re.IGNORECASE,
)
_ACTION = re.compile(
    r"\b(?:turn\s+(?:on|off)|set|create|delete|remove|add|send|email|message|schedule|"
    r"book|reserve|move|rename|upload|download|run|execute|install|update|save|post|"
    r"publish|call|remind|cancel|start|stop|open|close)\b",
    re.IGNORECASE,
)
_ACTION_TARGET = re.compile(
    r"\b(?:light|brightness|thermostat|calendar|event|meeting|email|message|file|folder|"
    r"document|app|application|service|job|task|reminder|reservation|booking|device|"
    r"room|system|repository|branch|pull request|issue|download|upload)\b",
    re.IGNORECASE,
)
_INFORMATIONAL = re.compile(
    r"^(?:what|why|when|where|who|how|tell me|explain|describe|summarize|compare|"
    r"do you think|what do you think|is|are|was|were)\b",
    re.IGNORECASE,
)
_POLITE_ACTION = re.compile(
    r"^(?:can|could|would|will)\s+you\s+.+",
    re.IGNORECASE,
)
_CASUAL = re.compile(
    r"^(?:hi|hello|hey|thanks|thank you|good morning|good afternoon|good evening|"
    r"how are you|what's up|whats up)[.!?\s]*$",
    re.IGNORECASE,
)


class LiveAgentRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    auto_route_enabled: bool = False
    require_hermes: bool = True
    hermes_enabled: bool = False
    planner_timeout_seconds: float = Field(default=6.0, ge=1.0, le=30.0)


class LiveAgentRouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route: LiveAgentRoute
    requested_mode: LiveAgentRequestedMode
    automatic: bool = False
    confidence: float = Field(ge=0, le=1)
    reason: str
    proposal_only: bool = True
    review_required: bool = True
    executes: bool = False
    hermes_required: bool = True


def live_agent_runtime_config() -> LiveAgentRuntimeConfig:
    return LiveAgentRuntimeConfig(
        enabled=_flag("OMNIX_LIVE_AGENT_ENABLED"),
        auto_route_enabled=_flag("OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED"),
        require_hermes=_flag("OMNIX_LIVE_AGENT_REQUIRE_HERMES", default=True),
        hermes_enabled=_flag("HERMES_ENABLED"),
        planner_timeout_seconds=_float("OMNIX_LIVE_AGENT_TIMEOUT_SECONDS", 6.0, 1.0, 30.0),
    )


def classify_live_agent_intent(text: str) -> tuple[bool, float, str]:
    normalized = " ".join(str(text or "").strip().split())
    if not normalized:
        return False, 0.0, "empty"
    if _CASUAL.match(normalized):
        return False, 0.98, "casual_conversation"
    if _EXPLICIT_AGENT.search(normalized):
        return True, 0.99, "explicit_agent_request"
    action = bool(_ACTION.search(normalized))
    target = bool(_ACTION_TARGET.search(normalized))
    if _POLITE_ACTION.match(normalized) and action and target:
        return True, 0.91, "polite_action_request"
    if _INFORMATIONAL.match(normalized) and not (action and target):
        return False, 0.93, "informational_request"
    if action and target:
        return True, 0.86, "action_with_target"
    if action:
        return False, 0.55, "ambiguous_action"
    return False, 0.88, "conversation"


def resolve_live_agent_route(
    *,
    content: str,
    requested_mode: LiveAgentRequestedMode = "off",
    agent_mode: bool = False,
    user_turn_id: str | None = None,
    speech_segment_id: str | None = None,
    config: LiveAgentRuntimeConfig | None = None,
) -> LiveAgentRouteDecision:
    runtime = config or live_agent_runtime_config()
    explicit = agent_mode or requested_mode == "agent"
    is_live_voice = _is_live_voice_turn(user_turn_id, speech_segment_id)

    if explicit:
        return LiveAgentRouteDecision(
            route="agent_plan",
            requested_mode="agent",
            automatic=False,
            confidence=1.0,
            reason="explicit_agent_mode",
            hermes_required=False,
        )
    if requested_mode == "off" and not is_live_voice:
        return _direct("off", "not_live_voice", 1.0, runtime.require_hermes)
    if not runtime.enabled:
        return _direct(requested_mode, "live_agent_disabled", 1.0, runtime.require_hermes)
    if not runtime.auto_route_enabled:
        return _direct(requested_mode, "auto_route_disabled", 1.0, runtime.require_hermes)
    if not is_live_voice and requested_mode != "auto":
        return _direct(requested_mode, "auto_route_not_requested", 1.0, runtime.require_hermes)

    task, confidence, reason = classify_live_agent_intent(content)
    if not task:
        return _direct("auto", reason, confidence, runtime.require_hermes)
    if runtime.require_hermes and not runtime.hermes_enabled:
        return _direct("auto", "hermes_disabled", 1.0, runtime.require_hermes)
    return LiveAgentRouteDecision(
        route="agent_plan",
        requested_mode="auto",
        automatic=True,
        confidence=confidence,
        reason=reason,
        hermes_required=runtime.require_hermes,
    )


def _direct(
    requested_mode: LiveAgentRequestedMode,
    reason: str,
    confidence: float,
    hermes_required: bool,
) -> LiveAgentRouteDecision:
    return LiveAgentRouteDecision(
        route="direct_chat",
        requested_mode=requested_mode,
        automatic=requested_mode == "auto",
        confidence=confidence,
        reason=reason,
        proposal_only=True,
        review_required=False,
        executes=False,
        hermes_required=hermes_required,
    )


def _is_live_voice_turn(user_turn_id: str | None, speech_segment_id: str | None) -> bool:
    return str(user_turn_id or "").startswith("voice-user-turn:") or str(
        speech_segment_id or ""
    ).startswith("voice-segment:")


def _flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))
