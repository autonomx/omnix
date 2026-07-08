"""Backend-owned Chat memory scope resolution."""
from __future__ import annotations

import os
import re

from .models import MemoryScope, MemoryScopeContext

DEFAULT_PROFILE_ID = "profile:local"
DEFAULT_WORKSPACE_ID = "workspace:default"
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")


def _trusted_identifier(value: str | None, fallback: str | None = None) -> str | None:
    text = (value or "").strip()
    if not text:
        return fallback
    if not _IDENTIFIER_PATTERN.fullmatch(text):
        raise ValueError("memory scope identifiers must use stable local identifier characters")
    return text


def resolve_chat_scope(
    session_id: str,
    *,
    profile_id: str | None = None,
    workspace_id: str | None = None,
    project_id: str | None = None,
) -> MemoryScopeContext:
    """Resolve scope from server-owned inputs, never an arbitrary Chat request payload."""

    resolved_profile = _trusted_identifier(
        profile_id or os.environ.get("OMNIX_CHAT_PROFILE_ID"),
        DEFAULT_PROFILE_ID,
    )
    resolved_workspace = _trusted_identifier(
        workspace_id or os.environ.get("OMNIX_CHAT_WORKSPACE_ID"),
        DEFAULT_WORKSPACE_ID,
    )
    return MemoryScopeContext(
        profile_id=resolved_profile or DEFAULT_PROFILE_ID,
        workspace_id=resolved_workspace or DEFAULT_WORKSPACE_ID,
        project_id=_trusted_identifier(project_id),
        session_id=_trusted_identifier(session_id) or session_id,
    )


def scope_id_for(scope: MemoryScope, context: MemoryScopeContext) -> str | None:
    if scope == "global":
        return context.profile_id
    if scope == "workspace":
        return context.workspace_id
    if scope == "project":
        return context.project_id
    return context.session_id
