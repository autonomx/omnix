"""Stable Chat services and data types consumed by neighboring features."""
from __future__ import annotations

from app.chat.compaction import build_deterministic_summary, compaction_enabled
from app.chat.context_budget import PromptBudget, prompt_budget_from_env
from app.chat.live_call_prewarm import live_call_provider_affinity
from app.chat.live_chat_async_sse_bridge import eager_async_sse_stream
from app.chat.memory_prompt import resolve_prompt_memory
from app.chat.models import ChatMessage, ChatSession, SendChatMessageRequest
from app.chat.prompt_assembly import (
    PromptAssembly,
    build_prompt_assembly,
    resolve_system_session_identity,
)
from app.chat.prompt_window import build_prompt_assembly_with_window
from app.chat.provider_routing import resolve_effective_provider_id
from app.chat.prompt_rendering import (
    RenderedPrompt,
    RenderedPromptMessage,
    render_prompt_assembly,
)
from app.chat.provider_metrics import merge_provider_response_metrics
from app.chat.routing_deadline import provider_turn_deadline, remaining_turn_seconds
from app.chat.store import _model_key as model_key
from app.chat.store import _provider_key as provider_key
from app.conversation.contracts import estimate_tokens

__all__ = [
    "ChatMessage",
    "ChatSession",
    "PromptAssembly",
    "PromptBudget",
    "RenderedPrompt",
    "RenderedPromptMessage",
    "SendChatMessageRequest",
    "build_deterministic_summary",
    "build_prompt_assembly",
    "build_prompt_assembly_with_window",
    "compaction_enabled",
    "eager_async_sse_stream",
    "estimate_tokens",
    "live_call_provider_affinity",
    "merge_provider_response_metrics",
    "model_key",
    "prompt_budget_from_env",
    "provider_key",
    "provider_turn_deadline",
    "remaining_turn_seconds",
    "render_prompt_assembly",
    "resolve_prompt_memory",
    "resolve_effective_provider_id",
    "resolve_system_session_identity",
]
