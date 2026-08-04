"""Bounded prompt assembly for side-effect-free live generation."""
from __future__ import annotations

from typing import Any, Protocol

from app import shared
from app.chat.compaction import compaction_enabled
from app.chat.history_search import history_recall_enabled
from app.chat.models import ChatMessage, ChatSession
from app.chat.prompt_assembly import PromptAssembly, build_prompt_assembly
from app.chat.prompt_rendering import RenderedPrompt, render_prompt_assembly

LIVE_PROMPT_RECENT_MESSAGE_LIMIT = 12


class _PromptStore(Protocol):
    def build_provider_prompt(
        self,
        session: ChatSession,
        user_message: ChatMessage,
        context_items: list[dict[str, Any]] | None = None,
    ) -> tuple[PromptAssembly, RenderedPrompt]: ...


def live_prompt_fast_path_eligible(session: ChatSession) -> bool:
    """Use the bounded path only when it cannot omit active durable context."""

    return (
        not session.memory_enabled
        and not session.read_memory
        and session.shared_memory_access == "none"
        and not history_recall_enabled()
        and not compaction_enabled()
    )


def build_live_provider_prompt(
    store: _PromptStore,
    session: ChatSession,
    user_message: ChatMessage,
    context_items: list[dict[str, Any]] | None = None,
) -> tuple[PromptAssembly, RenderedPrompt]:
    """Skip optional repository lookups while preserving identity and recent turns.

    Sessions with memory, history recall, or compaction enabled use the canonical
    prompt path. Any assembly error also falls back, so the latency optimization
    never becomes a correctness dependency.
    """

    if not live_prompt_fast_path_eligible(session):
        return store.build_provider_prompt(session, user_message, context_items or [])
    try:
        assembly = build_prompt_assembly(
            session,
            user_message,
            global_system_prompt=shared.get_global_system_prompt(),
            context_items=context_items or [],
            recent_message_limit=LIVE_PROMPT_RECENT_MESSAGE_LIMIT,
        )
        assembly.diagnostics["live_prompt_fast_path"] = {
            "enabled": True,
            "recent_message_limit": LIVE_PROMPT_RECENT_MESSAGE_LIMIT,
            "skipped_lookups": [
                "approved_memory",
                "history_recall",
                "compaction_summary",
            ],
        }
        assembly.diagnostics["memory"] = {
            "memory_enabled": False,
            "reason": "live_prompt_fast_path",
        }
        assembly.diagnostics["history_recall"] = {
            "enabled": False,
            "retrieved_count": 0,
            "reason": "live_prompt_fast_path",
        }
        return assembly, render_prompt_assembly(assembly)
    except Exception:
        return store.build_provider_prompt(session, user_message, context_items or [])
