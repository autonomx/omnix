"""Legacy chat session compatibility routes for the web gateway."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class LegacySessionListItem(BaseModel):
    id: str
    title: str = "New Chat"
    updated_at: str = ""


class LegacySessionListResponse(BaseModel):
    success: bool = True
    sessions: list[LegacySessionListItem] = Field(default_factory=list)


class LegacySessionCreateResponse(BaseModel):
    success: bool = True
    session_id: str


class LegacySessionResponse(BaseModel):
    success: bool = True
    session: dict[str, Any]


class LegacySuccessResponse(BaseModel):
    success: bool = True


class LegacySessionUpdateRequest(BaseModel):
    title: str | None = None
    system_prompt: str | None = None


class LegacyGenerateTitleRequest(BaseModel):
    user_message: str = ""
    ai_response: str = ""


class LegacyGenerateTitleResponse(BaseModel):
    success: bool = True
    title: str


def list_legacy_sessions() -> LegacySessionListResponse:
    from app.shared import load_sessions

    sessions = load_sessions()
    items = sorted(
        [
            LegacySessionListItem(
                id=str(session_id),
                title=str(session.get("title") or "New Chat") if isinstance(session, dict) else "New Chat",
                updated_at=str(session.get("updated_at") or "") if isinstance(session, dict) else "",
            )
            for session_id, session in sessions.items()
        ],
        key=lambda item: item.updated_at,
        reverse=True,
    )
    return LegacySessionListResponse(sessions=items)


def create_legacy_session() -> LegacySessionCreateResponse:
    from app.shared import get_global_system_prompt, load_sessions, save_sessions

    sessions = load_sessions()
    session_id = str(uuid4())[:8]
    now = datetime.now().isoformat()
    sessions[session_id] = {
        "title": "New Chat",
        "messages": [],
        "system_prompt": get_global_system_prompt(),
        "created_at": now,
        "updated_at": now,
    }
    save_sessions(sessions)
    return LegacySessionCreateResponse(session_id=session_id)


def get_legacy_session(session_id: str) -> LegacySessionResponse | None:
    from app.shared import load_sessions

    session = load_sessions().get(session_id)
    if not isinstance(session, dict):
        return None
    return LegacySessionResponse(session=session)


def update_legacy_session(session_id: str, request: LegacySessionUpdateRequest) -> LegacySuccessResponse | None:
    from app.shared import load_sessions, save_sessions

    sessions = load_sessions()
    session = sessions.get(session_id)
    if not isinstance(session, dict):
        return None
    if request.title is not None:
        session["title"] = request.title
    if request.system_prompt is not None:
        session["system_prompt"] = request.system_prompt
    session["updated_at"] = datetime.now().isoformat()
    save_sessions(sessions)
    return LegacySuccessResponse()


def delete_legacy_session(session_id: str) -> LegacySuccessResponse | None:
    from app.shared import load_sessions, save_sessions

    sessions = load_sessions()
    if session_id not in sessions:
        return None
    del sessions[session_id]
    save_sessions(sessions)
    return LegacySuccessResponse()


def generate_legacy_session_title(request: LegacyGenerateTitleRequest) -> LegacyGenerateTitleResponse:
    first_line = request.user_message.split("\n")[0].strip() if request.user_message else ""
    if not first_line:
        first_line = request.ai_response.split("\n")[0].strip() if request.ai_response else ""
    return LegacyGenerateTitleResponse(title=(first_line[:50] if first_line else "New Chat"))
