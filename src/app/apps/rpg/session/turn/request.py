"""What a turn asks for: its kind, the submission it answers, and what the player gave (roadmap §4.1)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# player_text: the composer. structured_action: loadout, map and tactical actions, practice, quick actions,
# Hermes commands, rewind. world_tick: idle resume, ambient and spatial ticks, continue. system: upcasts only.
TurnKind = Literal["player_text", "structured_action", "world_tick", "system"]


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: TurnKind
    session_id: str = Field(min_length=1)
    submission_id: str = ""
    based_on_revision: int | None = None
    text: str = ""
    action: dict[str, Any] = Field(default_factory=dict)
    elapsed_minutes: int = Field(default=0, ge=0)


__all__ = ["TurnKind", "TurnRequest"]
