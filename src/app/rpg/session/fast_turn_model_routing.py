from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

MODEL_ROUTING_VERSION = "fast_turn_model_routing_v1"

FAST_ROUTINE_MODES = {"dialogue_fast", "service_fast", "travel_fast", "investigation_fast", "combat_event_fast"}
LARGE_BEAT_MODES = {"story_beat_high_quality", "scene_intro_high_quality", "major_reveal_high_quality"}
BACKGROUND_MODES = {"recap_background", "memory_background", "validator_background", "audit_background"}

_DEFAULT_BUDGETS = {
    "dialogue_fast": 140,
    "service_fast": 120,
    "travel_fast": 160,
    "investigation_fast": 160,
    "combat_event_fast": 80,
    "combat_round_summary": 140,
    "story_beat_high_quality": 450,
    "scene_intro_high_quality": 450,
    "major_reveal_high_quality": 420,
    "recap_background": 260,
    "memory_background": 120,
    "validator_background": 120,
    "audit_background": 120,
}


@dataclass(frozen=True)
class FastTurnModelRoute:
    format_version: str
    mode: str
    tier: str
    provider_id: str | None
    model_id: str | None
    max_output_tokens: int
    stream: bool
    blocking: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "mode": self.mode,
            "tier": self.tier,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "max_output_tokens": self.max_output_tokens,
            "stream": self.stream,
            "blocking": self.blocking,
            "reason": self.reason,
        }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _int(value: Any, default: int, *, minimum: int = 20, maximum: int = 800) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except Exception:
        return default
    return max(minimum, min(maximum, parsed))


def classify_fast_turn_mode(player_input: str, action: Mapping[str, Any] | None = None) -> str:
    """Classify a player action into a routing mode without an LLM call."""

    action = _mapping(action)
    action_type = _text(action.get("action_type") or action.get("semantic_action_type")).casefold()
    text = _text(player_input).casefold()
    if "combat" in action_type or any(term in text for term in ("attack", "shoot", "stab", "cast", "run turn")):
        return "combat_event_fast"
    if action_type in {"service", "commerce", "economy"} or any(term in text for term in ("buy", "sell", "room", "meal", "ration")):
        return "service_fast"
    if action_type in {"travel", "exploration"} or any(term in text for term in ("travel", "go to", "head to", "walk to")):
        return "travel_fast"
    if action_type in {"investigate", "observe", "search"} or any(term in text for term in ("look", "search", "inspect", "investigate", "listen")):
        return "investigation_fast"
    return "dialogue_fast"


def _tier_for_mode(mode: str) -> tuple[str, str]:
    if mode in FAST_ROUTINE_MODES or mode == "combat_round_summary":
        return "fast", "routine_player_facing_turn"
    if mode in LARGE_BEAT_MODES:
        return "large", "major_story_beat"
    if mode in BACKGROUND_MODES:
        return "small", "background_non_blocking_work"
    return "medium", "default_rpg_narration"


def _env_model(tier: str) -> str | None:
    return os.environ.get(f"RPG_{tier.upper()}_MODEL_ID") or os.environ.get("RPG_FAST_MODEL_ID")


def _env_provider(tier: str) -> str | None:
    return os.environ.get(f"RPG_{tier.upper()}_PROVIDER_ID") or os.environ.get("RPG_FAST_PROVIDER_ID")


def select_fast_turn_model_route(
    *,
    mode: str,
    provider_id: str | None = None,
    model_id: str | None = None,
    max_output_tokens: int | None = None,
    stream: bool | None = None,
) -> FastTurnModelRoute:
    """Return model tier and token budget for a fast-turn narration mode."""

    normalized_mode = _text(mode) or "dialogue_fast"
    tier, reason = _tier_for_mode(normalized_mode)
    budget = _int(max_output_tokens, _DEFAULT_BUDGETS.get(normalized_mode, 180), minimum=20, maximum=800)
    return FastTurnModelRoute(
        format_version=MODEL_ROUTING_VERSION,
        mode=normalized_mode,
        tier=tier,
        provider_id=provider_id or _env_provider(tier),
        model_id=model_id or _env_model(tier),
        max_output_tokens=budget,
        stream=True if stream is None and tier != "small" else bool(stream),
        blocking=tier != "small",
        reason=reason,
    )


def route_for_player_turn(
    player_input: str,
    *,
    action: Mapping[str, Any] | None = None,
    provider_id: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    mode = classify_fast_turn_mode(player_input, action)
    return select_fast_turn_model_route(mode=mode, provider_id=provider_id, model_id=model_id).as_dict()
