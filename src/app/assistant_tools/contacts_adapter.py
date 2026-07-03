"""Contacts runtime adapter foundation for assistant tools."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .models import AssistantToolRequest, AssistantToolResult


@dataclass(frozen=True)
class ContactRecord:
    id: str
    name: str
    email: str


class ContactsRuntimeAdapter(Protocol):
    def search_contacts(self, query: str, limit: int = 10) -> list[ContactRecord]: ...

    def resolve_recipient(self, query: str) -> ContactRecord | None: ...


@dataclass
class FakeContactsRuntimeAdapter:
    contacts: list[ContactRecord] = field(default_factory=list)

    def search_contacts(self, query: str, limit: int = 10) -> list[ContactRecord]:
        needle = query.lower().strip()
        if not needle:
            return self.contacts[:limit]
        return [contact for contact in self.contacts if needle in contact.name.lower() or needle in contact.email.lower()][:limit]

    def resolve_recipient(self, query: str) -> ContactRecord | None:
        matches = self.search_contacts(query, limit=1)
        return matches[0] if matches else None


def default_fake_contacts_adapter() -> FakeContactsRuntimeAdapter:
    return FakeContactsRuntimeAdapter(
        contacts=[
            ContactRecord(id="contact-1", name="Ada Lovelace", email="ada@example.com"),
            ContactRecord(id="contact-2", name="Grace Hopper", email="grace@example.com"),
        ]
    )


_DEFAULT_CONTACTS_ADAPTER = default_fake_contacts_adapter()


def get_contacts_runtime_adapter() -> ContactsRuntimeAdapter:
    return _DEFAULT_CONTACTS_ADAPTER


def run_contacts_tool_request(request: AssistantToolRequest, adapter: ContactsRuntimeAdapter | None = None) -> AssistantToolResult:
    runtime = adapter or get_contacts_runtime_adapter()
    query = str(request.input.get("query") or request.input.get("q") or "")
    if request.action_id == "contacts.search_contacts":
        contacts = runtime.search_contacts(query, limit=int(request.input.get("limit") or 10))
        return AssistantToolResult(
            tool_id=request.tool_id,
            action_id=request.action_id,
            session_id=request.session_id,
            risk_level="low",
            state_changed=False,
            result_summary=f"Found {len(contacts)} contact{'s' if len(contacts) != 1 else ''}.",
            output={"contacts": [contact.__dict__ for contact in contacts]},
        )
    if request.action_id == "contacts.resolve_recipient":
        contact = runtime.resolve_recipient(query)
        return AssistantToolResult(
            tool_id=request.tool_id,
            action_id=request.action_id,
            session_id=request.session_id,
            risk_level="medium",
            state_changed=False,
            result_summary=f"Resolved recipient {contact.email}." if contact else "No matching recipient found.",
            output={"contact": contact.__dict__ if contact else None},
        )
    return AssistantToolResult(
        tool_id=request.tool_id,
        action_id=request.action_id,
        session_id=request.session_id,
        error="contacts_action_not_available",
    )
