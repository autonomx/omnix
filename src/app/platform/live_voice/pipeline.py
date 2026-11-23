"""Explicit live-voice prompt pipeline.

The former runtime hook order was profile, spoken style, companion context,
prompt cache, then dependency timings. The profile wrapper selected the live
path; companion context replaced its prompt builder; the cache and dependency
wrappers surrounded that builder; spoken style ran after rendering. Keep that
effective call order here as ordinary feature-owned stages.
"""
from __future__ import annotations

from app.conversation.contracts import is_live_voice_message
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import logging
import time
from typing import Any
from contextvars import Token

from app.platform.chat.contracts import ChatMessage, ChatSession, PromptAssembly, RenderedPrompt

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LiveVoicePromptContext:
    store: Any
    session: ChatSession
    user_message: ChatMessage
    context_items: list[dict[str, Any]] | None
    assembly: PromptAssembly | None = None
    rendered: RenderedPrompt | None = None
    profile: Any | None = None  # the person's Live Chat settings, read once per turn
    settings_scope: AbstractContextManager[None] | None = None
    dependency_token: Token[dict[str, Any] | None] | None = None
    dependency_timings: dict[str, Any] | None = None
    cache_token: Token[dict[str, Any] | None] | None = None
    cache_timings: dict[str, Any] | None = None
    started_at: float | None = None


@dataclass(frozen=True, slots=True)
class LiveVoicePromptStage:
    name: str
    apply: Callable[[LiveVoicePromptContext], LiveVoicePromptContext]


def _profile_selection_stage(
    context: LiveVoicePromptContext,
) -> LiveVoicePromptContext:
    if not is_live_voice_message(context.user_message):
        raise ValueError("live_voice_prompt_requires_voice_turn")
    return context


def _dependency_settings_stage(
    context: LiveVoicePromptContext,
) -> LiveVoicePromptContext:
    from app.platform.live_voice.prompt.dependency_stages import (
        begin_dependency_timings,
        use_cached_memory_runtime_settings,
    )

    context.dependency_token, context.dependency_timings = begin_dependency_timings()
    context.settings_scope = use_cached_memory_runtime_settings()
    context.settings_scope.__enter__()
    return context


def _prompt_cache_stage(
    context: LiveVoicePromptContext,
) -> LiveVoicePromptContext:
    from app.platform.live_voice.prompt.cache import begin_prompt_stage_timings

    context.started_at = time.perf_counter()
    context.cache_token, context.cache_timings = begin_prompt_stage_timings()
    return context


def _companion_context_stage(
    context: LiveVoicePromptContext,
) -> LiveVoicePromptContext:
    from app.platform.live_voice.prompt.companion_context import build_companion_prompt, load_live_profile

    context.profile = load_live_profile(context.session.id)
    context.assembly, context.rendered = build_companion_prompt(
        context.store,
        context.session,
        context.user_message,
        context.context_items,
        profile=context.profile,
    )
    return context


def _spoken_style_stage(
    context: LiveVoicePromptContext,
) -> LiveVoicePromptContext:
    from app.platform.live_voice.prompt.spoken_style import (
        apply_live_voice_spoken_style,
        record_spoken_style_diagnostics,
    )

    if context.assembly is None or context.rendered is None:
        raise RuntimeError("live_voice_prompt_assembly_missing")
    apply_live_voice_spoken_style(context.rendered, context.profile)
    record_spoken_style_diagnostics(context.assembly, context.rendered)
    _add_call_abilities(context)
    _add_sound_tags(context)
    return context


def _add_sound_tags(context: LiveVoicePromptContext) -> None:
    """Offer the sound tags the call's voice has clips for (``prompt.sound_tags``), after the abilities."""
    from app.conversation.contracts import estimate_tokens
    from app.platform.chat.contracts import RenderedPromptMessage
    from app.platform.live_voice.prompt.cache import resolve_live_voice_speaker_cached
    from app.platform.live_voice.prompt.sound_tags import offered_sound_tags, sound_tags_prompt
    from app.platform.live_voice.transport.cue_asset_routes import voice_cue_ids

    rendered = context.rendered
    if rendered is None:
        return
    tags = offered_sound_tags(context.profile, voice_cue_ids(resolve_live_voice_speaker_cached(context.session)))
    instructions = sound_tags_prompt(tags)
    if not instructions:
        return
    first_turn = next(
        (index for index, message in enumerate(rendered.messages) if message.role in {"user", "assistant"}),
        len(rendered.messages),
    )
    rendered.messages.insert(first_turn, RenderedPromptMessage(role="system", content=instructions))
    tokens = estimate_tokens(instructions)
    rendered.diagnostics.estimated_tokens += tokens
    rendered.diagnostics.section_tokens["live_voice_sound_tags"] = tokens
    if context.assembly is not None:
        context.assembly.diagnostics["live_voice_sound_tags"] = {"tags": list(tags), "tokens": tokens}


def _add_call_abilities(context: LiveVoicePromptContext) -> None:
    """How to ask for the abilities the speaker was granted (``llm.call_tools``), after the spoken style.

    Stable across a call's turns, so the system prompt still chooses the waiting process. None granted: nothing added.
    The actions on offer, the current time and the call's tasks change between turns, so they go in the per-turn part.
    """
    from app.conversation.contracts import estimate_tokens
    from app.platform.chat.contracts import RenderedPromptMessage
    from app.platform.live_voice.llm.call_tools import abilities_prompt, actions_catalog, offered_abilities

    offered = offered_abilities(context.session)
    instructions = abilities_prompt(offered)
    rendered = context.rendered
    if rendered is None:
        return
    added = []
    if instructions:
        added.append(RenderedPromptMessage(role="system", content=instructions))
        catalog = actions_catalog(offered)
        if catalog:
            added.append(RenderedPromptMessage(role="system", content=catalog, per_turn=True))
    # Tasks still running are told even when the ability was withdrawn mid-call.
    tasks = _call_tasks_state(context.session)
    if tasks:
        added.append(RenderedPromptMessage(role="system", content=tasks, per_turn=True))
    if not added:
        return
    first_turn = next(
        (index for index, message in enumerate(rendered.messages) if message.role in {"user", "assistant"}),
        len(rendered.messages),
    )
    rendered.messages[first_turn:first_turn] = added
    tokens = sum(estimate_tokens(message.content) for message in added)
    rendered.diagnostics.estimated_tokens += tokens
    rendered.diagnostics.section_tokens["live_voice_abilities"] = tokens
    if context.assembly is not None:
        context.assembly.diagnostics["live_voice_abilities"] = {
            **{ability: True for ability, on in offered.items() if on}, "tasks": bool(tasks), "tokens": tokens,
        }


def _call_tasks_state(session: Any) -> str | None:
    """The call's tasks as their records say (``chat.live_call_tasks``); a failed read leaves them out of this turn."""
    from app.platform.chat.contracts import call_tasks_prompt

    try:
        return call_tasks_prompt(session)
    except Exception:  # noqa: BLE001 - the turn goes on without the task list
        logger.warning("live voice: the call's tasks could not be read", exc_info=True)
        return None


def _finish_prompt_stages(context: LiveVoicePromptContext) -> None:
    total_ms = (
        (time.perf_counter() - context.started_at) * 1000.0
        if context.started_at is not None
        else 0.0
    )
    from app.platform.live_voice.prompt.dependency_stages import end_dependency_timings

    try:
        if context.started_at is not None:
            from app.platform.live_voice.prompt.cache import end_prompt_stage_timings

            if context.cache_token is not None and context.cache_timings is not None:
                end_prompt_stage_timings(
                    context.cache_token,
                    context.cache_timings,
                    session=context.session,
                    total_ms=total_ms,
                )
    finally:
        try:
            if context.dependency_token is not None and context.dependency_timings is not None:
                end_dependency_timings(
                    context.dependency_token,
                    context.dependency_timings,
                    session=context.session,
                    total_ms=total_ms,
                )
        finally:
            if context.settings_scope is not None:
                context.settings_scope.__exit__(None, None, None)


# Keep the stage list executable so prompt composition cannot depend on module
# import or gateway initialization order.
LIVE_VOICE_PROMPT_STAGES = (
    LiveVoicePromptStage("profile_selection", _profile_selection_stage),
    LiveVoicePromptStage("dependency_settings", _dependency_settings_stage),
    LiveVoicePromptStage("prompt_cache", _prompt_cache_stage),
    LiveVoicePromptStage("companion_context", _companion_context_stage),
    LiveVoicePromptStage("spoken_style", _spoken_style_stage),
)


def build_live_voice_prompt(
    store: Any,
    session: ChatSession,
    user_message: ChatMessage,
    context_items: list[dict[str, Any]] | None = None,
) -> tuple[PromptAssembly, RenderedPrompt]:
    """Run each feature-owned stage and return its assembled prompt."""
    context = LiveVoicePromptContext(
        store=store,
        session=session,
        user_message=user_message,
        context_items=context_items,
    )
    try:
        for stage in LIVE_VOICE_PROMPT_STAGES:
            context = stage.apply(context)
    finally:
        _finish_prompt_stages(context)
    if context.assembly is None or context.rendered is None:
        raise RuntimeError("live_voice_prompt_pipeline_incomplete")
    return context.assembly, context.rendered


__all__ = [
    "LIVE_VOICE_PROMPT_STAGES",
    "LiveVoicePromptContext",
    "LiveVoicePromptStage",
    "build_live_voice_prompt",
    "is_live_voice_message",
]
