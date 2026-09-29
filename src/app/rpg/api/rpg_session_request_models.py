"""Typed request bodies for RPG session API endpoints."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _TypedRequestModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class GetRpgSessionRequestBody(_TypedRequestModel):
    session_id: Any = None


class ExecuteRpgSessionTurnRequestBody(_TypedRequestModel):
    session_id: str | None = None
    player_input: str | None = None
    action: dict[str, Any] | None = None
    runtime_settings: dict[str, Any] | None = None


class ExecuteRpgSessionTurnStreamRequestBody(_TypedRequestModel):
    session_id: str | None = None
    player_input: str | None = None
    action: dict[str, Any] | None = None
    runtime_settings: dict[str, Any] | None = None
    performance: dict[str, Any] | None = None


class ProcessRpgSessionNarrationRequestBody(_TypedRequestModel):
    session_id: Any = None


class GetRpgSessionNarrationStatusRequestBody(_TypedRequestModel):
    session_id: Any = None
    turn_id: Any = None


class PollRpgSessionRequestBody(_TypedRequestModel):
    after_seq: int | None = 0
    limit: int | None = 8
    session_id: Any = None


class ResumeRpgSessionRequestBody(_TypedRequestModel):
    elapsed_seconds: int | None = 0
    session_id: Any = None


class RpgSessionConversationInterveneRequestBody(_TypedRequestModel):
    conversation_id: Any = None
    option_id: Any = None
    session_id: Any = None
