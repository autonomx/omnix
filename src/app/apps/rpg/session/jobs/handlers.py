"""RPG durable job contracts."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RpgTurnJobInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    command: str
    provider_id: str | None = None
    model_id: str | None = None


class RpgReportJobInput(BaseModel):
    model_config = ConfigDict(extra="allow")


class RpgNarrationJobInput(BaseModel):
    """One deferred narration request (``rpg.narration``, WP-5.6)."""

    model_config = ConfigDict(extra="allow")
    session_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    interaction_id: str = ""
    tick: int = 0
    job_kind: str = "player_turn"
    narration_request: dict[str, Any] = Field(default_factory=dict)
