"""When a turn may use generative UI, and the instruction that teaches the format (GUI-3.1, GUI-3.2).

``ui_enabled_for_turn`` is the one decision: the session's ``rich_replies`` is
"on", the model's evaluated level is not "none", and the turn is not a live
voice, character, agent, deep-research or memory-command turn. Prompt assembly
uses it twice: the history projection (``MODEL_RICH`` or ``MODEL``, invariant 5)
and whether ``catalog_instruction`` is added to the system instructions.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from app.conversation.contracts import estimate_tokens

from .catalog import CATALOG

RichUiLevel = Literal["none", "basic", "full"]
CapabilityLookup = Callable[[str | None, str | None], RichUiLevel]

BASIC_BLOCKS = ("stats", "chart")
FULL_BLOCKS = ("stats", "chart", "price_chart", "sources", "choices", "form")


@dataclass(frozen=True)
class RichReplyDecision:
    enabled: bool
    level: RichUiLevel
    reason: str
    provider_id: str | None = None
    model_id: str | None = None

    def diagnostics(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "level": self.level,
            "reason": self.reason,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
        }


DISABLED = RichReplyDecision(False, "none", "not_requested")


def _default_capability(provider_id: str | None, model_id: str | None) -> RichUiLevel:
    from app.providers.model_catalog import rich_ui_capability

    return rich_ui_capability(provider_id, model_id)


def _metadata(message: Any) -> Mapping[str, Any]:
    metadata = getattr(message, "metadata", None)
    return metadata if isinstance(metadata, Mapping) else {}


def turn_model(session: Any, user_message: Any, provider_id: str | None = None, model_id: str | None = None) -> tuple[str | None, str | None]:
    """The provider and model that answer the turn: a recorded route first, then the request, then the session."""
    route = _metadata(user_message).get("omnix_provider_route")
    if isinstance(route, Mapping) and route.get("provider_id"):
        return str(route.get("provider_id")), str(route.get("model_id") or "") or None
    return provider_id or getattr(session, "provider_id", None), model_id or getattr(session, "model_id", None)


def excluded_turn_mode(session: Any, user_message: Any) -> str | None:
    """Why this kind of turn never gets rich replies, or None."""
    metadata = _metadata(user_message)
    if str(metadata.get("speech_segment_id") or "").strip() or str(metadata.get("user_turn_id") or "").startswith("voice-user-turn:"):
        return "live_voice"
    if getattr(session, "interaction_mode", "system") == "character":
        return "character_mode"
    route = metadata.get("omnix_route")
    if metadata.get("agent_mode") is True or (isinstance(route, Mapping) and route.get("lane") == "agent"):
        return "agent_mode"
    if metadata.get("research_mode") == "deep":
        return "deep_research"
    if metadata.get("memory_command"):
        return "memory_command"
    from ..memory_port import parse_memory_command

    if parse_memory_command(str(getattr(user_message, "content", "") or "")) is not None:
        return "memory_command"
    return None


def ui_enabled_for_turn(
    session: Any,
    user_message: Any,
    *,
    provider_id: str | None = None,
    model_id: str | None = None,
    capability: CapabilityLookup | None = None,
) -> RichReplyDecision:
    """Whether this turn may answer with generative UI blocks, and at which level."""
    provider, model = turn_model(session, user_message, provider_id, model_id)
    if getattr(session, "rich_replies", None) != "on":
        return RichReplyDecision(False, "none", "session_setting_off", provider, model)
    level = (capability or _default_capability)(provider, model)
    if level == "none":
        return RichReplyDecision(False, "none", "model_not_enabled", provider, model)
    excluded = excluded_turn_mode(session, user_message)
    if excluded is not None:
        return RichReplyDecision(False, level, excluded, provider, model)
    return RichReplyDecision(True, level, "enabled", provider, model)


_EXAMPLE = (
    "Revenue held steady this quarter.\n\n"
    "```omnix-ui\n"
    '{"type": "stats", "items": [{"label": "Revenue", "value": "$6,930", "delta": "+4.1%", "trend": "up"}, '
    '{"label": "Orders", "value": "212"}]}\n'
    "```"
)


def catalog_instruction(level: RichUiLevel) -> str:
    """The system instruction for a rich-enabled turn, generated from the catalog; "" for "none"."""
    if level == "none":
        return ""
    blocks = BASIC_BLOCKS if level == "basic" else FULL_BLOCKS
    lines = [
        "This chat renders Markdown and a few interface blocks in your replies.",
        "- Prefer Markdown: tables, lists, task lists (- [ ] item) and alerts (> [!NOTE], > [!WARNING]).",
        "- Use a block only for "
        + ("headline numbers and charts" if level == "basic" else "headline numbers, charts, market data, sources and suggested next steps")
        + ". Most replies need none, and never put prose in a block.",
        "- Write each block as one JSON object in a fenced code block whose info string is omnix-ui.",
        "- Still state the key point in prose: some readers only see text.",
        "Blocks:",
    ]
    lines.extend(f"- {name}: {CATALOG[name].summary}" for name in blocks)
    if "sources" in blocks:
        lines.append('- In "bind", source:N is the source you cite as [SN] and context:N is context item [N].')
    if "choices" in blocks:
        lines.append("- A choices label is sent as the user's own message: write it in the user's voice.")
    lines.extend(["Example:", _EXAMPLE])
    return "\n".join(lines)


def catalog_instruction_tokens(level: RichUiLevel) -> int:
    return estimate_tokens(catalog_instruction(level))
