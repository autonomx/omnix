from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CASUAL_PHRASES = {
    "yeah",
    "yes",
    "ok",
    "okay",
    "sure",
    "thanks",
    "thank you",
    "tell me more",
    "interesting",
}
COMMAND_MARKERS = (
    "light",
    "brightness",
    "status",
    "remind",
    "podcast",
    "story",
    "rpg",
    "ask ",
    "scene",
    "quest",
)


@dataclass
class LiveGateResult:
    route: Literal["direct", "assistant"]
    reason: str


def route_live_text(text: str, *, assistant_mode: bool = False) -> LiveGateResult:
    normalized = " ".join(str(text or "").lower().split())
    if not assistant_mode:
        return LiveGateResult(route="direct", reason="assistant_mode_off")
    if not normalized:
        return LiveGateResult(route="direct", reason="empty")
    if normalized in CASUAL_PHRASES:
        return LiveGateResult(route="direct", reason="casual_phrase")
    if any(marker in normalized for marker in COMMAND_MARKERS):
        return LiveGateResult(route="assistant", reason="command_marker")
    return LiveGateResult(route="direct", reason="no_command_marker")
