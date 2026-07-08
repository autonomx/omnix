"""Deterministic explicit Chat memory commands."""
from __future__ import annotations

import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.assistant_memory import MemoryService, resolve_chat_scope

from .memory_session import RefreshSessionMemoryRequest, refresh_session_memory
from .models import ChatSession

MemoryCommandKind = Literal["save", "list", "forget", "refresh", "disable", "update"]


class MemoryCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: MemoryCommandKind
    content: str = ""
    scope: Literal["global", "workspace", "project", "session"] = "session"
    category: Literal["preference", "fact", "project", "relationship", "instruction"] = "fact"
    memory_id: str | None = None


class MemoryCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handled: bool = True
    content: str
    command: MemoryCommandKind
    mutated: bool
    memory_ids: list[str] = []


class SessionStoreLike(Protocol):
    def get_session(self, session_id: str) -> ChatSession | None: ...
    def _load_sessions(self) -> list[ChatSession]: ...
    def _save_sessions(self, sessions: list[ChatSession]) -> None: ...


_SAVE_PATTERN = re.compile(
    r"^save\s+as\s+(global|workspace|project|session)\s+"
    r"(preference|fact|project|relationship|instruction)\s*:\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_UPDATE_PATTERN = re.compile(r"^update\s+memory\s+(memory:[A-Za-z0-9_.-]+)\s*:\s*(.+)$", re.IGNORECASE | re.DOTALL)


def parse_memory_command(content: str) -> MemoryCommand | None:
    text = " ".join(content.strip().split())
    lowered = text.casefold()
    if lowered in {"what do you remember", "what do you remember?", "list memory", "list memories"}:
        return MemoryCommand(kind="list")
    if lowered in {"refresh memory", "refresh chat memory"}:
        return MemoryCommand(kind="refresh")
    if lowered in {"disable memory for this chat", "start without memory", "turn off memory for this chat"}:
        return MemoryCommand(kind="disable")
    match = _SAVE_PATTERN.match(text)
    if match:
        return MemoryCommand(
            kind="save",
            scope=match.group(1).casefold(),
            category=match.group(2).casefold(),
            content=match.group(3).strip(),
        )
    match = _UPDATE_PATTERN.match(text)
    if match:
        return MemoryCommand(kind="update", memory_id=match.group(1).strip(), content=match.group(2).strip())
    if lowered.startswith("remember that ") and len(text[14:].strip()) >= 3:
        return MemoryCommand(kind="save", content=text[14:].strip(), category="fact")
    if lowered.startswith("remember: ") and len(text[10:].strip()) >= 3:
        return MemoryCommand(kind="save", content=text[10:].strip(), category="fact")
    if lowered.startswith("forget ") and len(text[7:].strip()) >= 3:
        return MemoryCommand(kind="forget", content=text[7:].strip())
    return None


def _scope(session: ChatSession):
    return resolve_chat_scope(
        session.id,
        profile_id=session.profile_id,
        workspace_id=session.workspace_id,
        project_id=session.project_id,
    )


def execute_memory_command(
    store: SessionStoreLike,
    service: MemoryService,
    session_id: str,
    user_message_id: str,
    command: MemoryCommand,
) -> MemoryCommandResult:
    session = store.get_session(session_id)
    if session is None:
        return MemoryCommandResult(content="The Chat session no longer exists.", command=command.kind, mutated=False)
    context = _scope(session)

    if command.kind == "save":
        record = service.create_explicit_memory(
            context,
            scope=command.scope,
            category=command.category,
            content=command.content,
            provenance_id=user_message_id,
        )
        return MemoryCommandResult(
            content=f"Saved as {record.scope} {record.category} memory. Refresh this Chat's memory to use it in the active conversation.",
            command="save",
            mutated=True,
            memory_ids=[record.id],
        )

    if command.kind == "list":
        records = service.list_active(context)
        if not records:
            return MemoryCommandResult(content="I do not have any approved memory available in this Chat's scope.", command="list", mutated=False)
        lines = [f"- [{record.scope}/{record.category}] {record.content}" for record in records]
        return MemoryCommandResult(
            content="Approved memory available to this Chat:\n" + "\n".join(lines),
            command="list",
            mutated=False,
            memory_ids=[record.id for record in records],
        )

    if command.kind == "forget":
        needle = " ".join(command.content.split()).casefold()
        matches = [record for record in service.list_active(context) if needle in record.normalized_content]
        if not matches:
            return MemoryCommandResult(content="No approved memory matched that description, so nothing was changed.", command="forget", mutated=False)
        if len(matches) > 1:
            choices = "\n".join(f"- {record.id}: {record.content}" for record in matches[:10])
            return MemoryCommandResult(content="More than one memory matched. Use `forget <unique text>` or the Memory view:\n" + choices, command="forget", mutated=False, memory_ids=[record.id for record in matches])
        record = matches[0]
        service.forget_memory(context, record.id, expected_revision=record.revision)
        return MemoryCommandResult(content="Forgot the matching memory and removed it from active snapshots.", command="forget", mutated=True, memory_ids=[record.id])

    if command.kind == "refresh":
        state = refresh_session_memory(
            store,
            service,
            session_id,
            RefreshSessionMemoryRequest(expected_snapshot_revision=session.memory_snapshot_revision),
        )
        count = state.memory_record_count if state else 0
        revision = state.snapshot_revision if state else None
        return MemoryCommandResult(content=f"Refreshed active Chat memory to snapshot revision {revision} with {count} records.", command="refresh", mutated=True)

    if command.kind == "disable":
        sessions = store._load_sessions()
        for index, current in enumerate(sessions):
            if current.id != session_id:
                continue
            current.memory_enabled = False
            sessions[index] = current
            store._save_sessions(sessions)
            return MemoryCommandResult(content="Memory is disabled for this Chat. Saved records were not deleted.", command="disable", mutated=True)
        return MemoryCommandResult(content="The Chat session no longer exists.", command="disable", mutated=False)

    record = service.repository.get_record(command.memory_id or "")
    if record is None or record not in service.list_active(context):
        return MemoryCommandResult(content="That memory ID is not available in this Chat's scope.", command="update", mutated=False)
    updated = service.edit_memory(
        context,
        record.id,
        content=command.content,
        expected_revision=record.revision,
    )
    return MemoryCommandResult(content="Updated the memory. Refresh active Chat memory to use the revised text.", command="update", mutated=True, memory_ids=[updated.id])
