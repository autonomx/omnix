"""Authoritative privacy and transcript-retention decisions for Chat turns."""
from __future__ import annotations

from typing import Any

from app.assistant_memory.settings import (
    AssistantMemoryRuntimeSettings,
    load_memory_runtime_settings,
)


def private_session(session: Any) -> bool:
    """Return whether a session is explicitly configured as non-persistent."""

    return str(getattr(session, "transcript_policy", "persistent") or "persistent") != "persistent"


def transcript_retention_allowed(
    session: Any,
    *,
    settings: AssistantMemoryRuntimeSettings | None = None,
) -> bool:
    """Decide whether new transcript and summary material may be persisted."""

    effective = settings or load_memory_runtime_settings()
    return not private_session(session) and effective.transcript_retention_enabled


def automatic_memory_derivation_allowed(session: Any) -> bool:
    """Private sessions never create automatic durable memory derivatives."""

    return not private_session(session)


def explicit_memory_mutation_allowed(session: Any, command_kind: str) -> bool:
    """Permit privacy-preserving removals but reject private durable writes."""

    if not private_session(session):
        return True
    return command_kind not in {"save", "update"}


__all__ = [
    "automatic_memory_derivation_allowed",
    "explicit_memory_mutation_allowed",
    "private_session",
    "transcript_retention_allowed",
]
