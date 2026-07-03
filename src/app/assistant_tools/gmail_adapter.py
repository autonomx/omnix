"""Gmail runtime adapter foundation for assistant tools."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import AssistantToolRequest, AssistantToolResult


@dataclass(frozen=True)
class GmailMessageRecord:
    id: str
    sender: str
    subject: str
    snippet: str
    thread_id: str | None = None


@dataclass(frozen=True)
class GmailDraftRecord:
    id: str
    to: str
    subject: str
    body: str


class GmailRuntimeAdapter(Protocol):
    def search_messages(self, query: str, limit: int = 10) -> list[GmailMessageRecord]: ...

    def create_draft(self, *, to: str, subject: str, body: str) -> GmailDraftRecord: ...

    def update_draft(self, *, draft_id: str, to: str | None = None, subject: str | None = None, body: str | None = None) -> GmailDraftRecord: ...


@dataclass
class FakeGmailRuntimeAdapter:
    messages: list[GmailMessageRecord] = field(default_factory=list)
    drafts: dict[str, GmailDraftRecord] = field(default_factory=dict)

    def search_messages(self, query: str, limit: int = 10) -> list[GmailMessageRecord]:
        needle = query.lower().strip()
        if not needle:
            return self.messages[:limit]
        matches = [
            message
            for message in self.messages
            if needle in message.sender.lower() or needle in message.subject.lower() or needle in message.snippet.lower()
        ]
        return matches[:limit]

    def create_draft(self, *, to: str, subject: str, body: str) -> GmailDraftRecord:
        draft = GmailDraftRecord(id=f"draft-{uuid.uuid4().hex[:12]}", to=to, subject=subject, body=body)
        self.drafts[draft.id] = draft
        return draft

    def update_draft(self, *, draft_id: str, to: str | None = None, subject: str | None = None, body: str | None = None) -> GmailDraftRecord:
        current = self.drafts.get(draft_id)
        if current is None:
            raise KeyError("draft_not_found")
        draft = GmailDraftRecord(
            id=current.id,
            to=to if to is not None else current.to,
            subject=subject if subject is not None else current.subject,
            body=body if body is not None else current.body,
        )
        self.drafts[draft.id] = draft
        return draft


def default_fake_gmail_adapter() -> FakeGmailRuntimeAdapter:
    return FakeGmailRuntimeAdapter(
        messages=[
            GmailMessageRecord(id="msg-1", sender="ada@example.com", subject="Receipt", snippet="Your order receipt is attached.", thread_id="thread-1"),
            GmailMessageRecord(id="msg-2", sender="team@example.com", subject="Project update", snippet="CI is green and the PR is ready.", thread_id="thread-2"),
        ]
    )


_DEFAULT_GMAIL_ADAPTER = default_fake_gmail_adapter()


def get_gmail_runtime_adapter() -> GmailRuntimeAdapter:
    return _DEFAULT_GMAIL_ADAPTER


def run_gmail_tool_request(request: AssistantToolRequest, adapter: GmailRuntimeAdapter | None = None) -> AssistantToolResult:
    runtime = adapter or get_gmail_runtime_adapter()
    if request.action_id == "gmail.read_email":
        query = str(request.input.get("query") or request.input.get("q") or "")
        limit = int(request.input.get("limit") or 10)
        messages = runtime.search_messages(query, limit=limit)
        return AssistantToolResult(
            tool_id=request.tool_id,
            action_id=request.action_id,
            session_id=request.session_id,
            risk_level="low",
            state_changed=False,
            result_summary=f"Found {len(messages)} Gmail message{'s' if len(messages) != 1 else ''}.",
            output={"messages": [message.__dict__ for message in messages]},
        )
    if request.action_id == "gmail.create_draft":
        draft = runtime.create_draft(
            to=str(request.input.get("to") or ""),
            subject=str(request.input.get("subject") or ""),
            body=str(request.input.get("body") or ""),
        )
        return AssistantToolResult(
            tool_id=request.tool_id,
            action_id=request.action_id,
            session_id=request.session_id,
            risk_level="medium",
            state_changed=True,
            result_summary=f"Created Gmail draft {draft.id} to {draft.to}.",
            output={"draft": draft.__dict__},
        )
    return AssistantToolResult(
        tool_id=request.tool_id,
        action_id=request.action_id,
        session_id=request.session_id,
        risk_level="high",
        state_changed=False,
        result_summary="Gmail action is approval-gated or not connected to a runtime adapter yet.",
        error="gmail_action_not_available",
    )
