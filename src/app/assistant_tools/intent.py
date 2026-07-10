"""Lightweight assistant tool intent detection for chat messages."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AssistantToolIntent(BaseModel):
    detected: bool = False
    tool_id: str | None = None
    action_id: str | None = None
    confidence: float = 0.0
    preview_title: str = ""
    preview_summary: str = ""
    input: dict[str, object] = Field(default_factory=dict)


def detect_assistant_tool_intent(message: str) -> AssistantToolIntent:
    text = message.lower().strip()
    if not text:
        return AssistantToolIntent()
    if any(term in text for term in ("email", "gmail", "draft")):
        action_id = "gmail.create_draft" if "draft" in text else "gmail.read_email"
        return AssistantToolIntent(
            detected=True,
            tool_id="gmail",
            action_id=action_id,
            confidence=0.72,
            preview_title="Gmail tool action",
            preview_summary="Review a Gmail action before it runs.",
            input={"query": message},
        )
    if any(term in text for term in ("schedule", "calendar", "availability", "meeting", "reminder", "remind me")):
        action_id = "calendar.create_event" if any(term in text for term in ("schedule", "create", "book", "reminder", "remind me")) else "calendar.read_availability"
        return AssistantToolIntent(
            detected=True,
            tool_id="calendar",
            action_id=action_id,
            confidence=0.7,
            preview_title="Calendar tool action",
            preview_summary="Review a calendar action before it runs.",
            input={"query": message},
        )
    if any(term in text for term in ("contact", "recipient", "phone number")):
        return AssistantToolIntent(
            detected=True,
            tool_id="contacts",
            action_id="contacts.search_contacts",
            confidence=0.68,
            preview_title="Contacts tool action",
            preview_summary="Review a contact lookup before it runs.",
            input={"query": message},
        )
    if any(term in text for term in ("pull request", "open pr", "check ci", "repo")):
        action_id = "github.create_pr" if "open" in text else "github.read_repo"
        return AssistantToolIntent(
            detected=True,
            tool_id="github",
            action_id=action_id,
            confidence=0.66,
            preview_title="GitHub tool action",
            preview_summary="Review a repository action before it runs.",
            input={"query": message},
        )
    return AssistantToolIntent()
