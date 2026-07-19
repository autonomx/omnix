"""Install deterministic companion packets on the bounded live-voice prompt path."""
from __future__ import annotations

from typing import Any

from app.assistant_memory.companion_context import build_companion_context_packet
from app.chat.compaction import compaction_enabled
from app.chat.memory_prompt import resolve_prompt_memory
from app.chat.prompt_assembly import build_prompt_assembly
from app.chat.prompt_rendering import render_prompt_assembly

from . import live_chat_live_voice_profile as live_profile
from .tts_stream_diagnostics import stream_log

_SENTINEL = "_omnix_companion_context_packet_installed"


def _build_companion_prompt(
    self: Any,
    session: Any,
    user_message: Any,
    context_items: list[dict[str, Any]] | None,
):
    from app import shared

    budget = live_profile._live_voice_prompt_budget()
    approved_memory, memory_diagnostics = resolve_prompt_memory(
        session,
        memory_service_factory=self.memory_service_factory,
    )
    packet = build_companion_context_packet(
        session,
        user_message,
        approved_memory,
        token_budget=budget.memory_tokens,
    )
    summary_record = (
        self.summary_repository_factory().latest(session.id)
        if compaction_enabled()
        else None
    )
    recent_message_limit = live_profile._live_voice_recent_message_limit()
    assembly = build_prompt_assembly(
        session,
        user_message,
        global_system_prompt=shared.get_global_system_prompt(),
        context_items=context_items or [],
        approved_memory=packet.prompt_memory,
        retrieved_history=[],
        session_summary=summary_record.summary if summary_record is not None else None,
        recent_message_limit=recent_message_limit,
        budget=budget,
    )
    assembly.diagnostics["memory"] = memory_diagnostics
    assembly.diagnostics["companion_context"] = packet.content_free_diagnostics()
    assembly.diagnostics["compaction"] = (
        {
            "enabled": True,
            "summary_id": summary_record.id,
            "summary_revision": summary_record.revision,
            "through_message_id": summary_record.through_message_id,
            "source_message_count": summary_record.source_message_count,
            "recent_message_limit": recent_message_limit,
        }
        if summary_record is not None
        else {
            "enabled": compaction_enabled(),
            "summary_id": None,
            "recent_message_limit": recent_message_limit,
        }
    )
    assembly.diagnostics["history_recall"] = {
        "enabled": False,
        "retrieved_count": 0,
        "reason": "companion_context_packet",
    }
    rendered = render_prompt_assembly(assembly)
    assembly.diagnostics["latency_profile"] = {
        "name": "live_voice_companion",
        "recent_message_limit": recent_message_limit,
        "max_input_tokens": budget.max_input_tokens,
        "reserved_output_tokens": budget.reserved_output_tokens,
        "memory_tokens": budget.memory_tokens,
        "summary_tokens": budget.summary_tokens,
        "history_tokens": budget.history_tokens,
        "external_context_tokens": budget.external_context_tokens,
        "estimated_tokens": rendered.diagnostics.estimated_tokens,
    }
    stream_log(
        "gateway-live-chat-first-token",
        "runtime",
        "live_chat_companion_context_packet",
        session_message_count=len(getattr(session, "messages", []) or []),
        selected_count=packet.selected_count,
        candidate_count=packet.candidate_count,
        packet_tokens=packet.token_estimate,
        packet_budget=packet.token_budget,
        packet_build_ms=round(packet.build_ms, 3),
        cache_hit=packet.cache_hit,
        truncated=packet.truncated,
    )
    return assembly, rendered


def install_live_chat_companion_context_hook() -> None:
    """Replace only the live prompt builder after the existing hook is installed."""

    if getattr(live_profile, _SENTINEL, False):
        return
    live_profile._build_live_voice_prompt = _build_companion_prompt
    setattr(live_profile, _SENTINEL, True)


__all__ = ["install_live_chat_companion_context_hook"]
