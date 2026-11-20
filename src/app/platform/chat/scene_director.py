"""Whether another member of the call reacts to a reply (companion 5.4): one word from the call's model.

The model only proposes a name. Code checks the reaction is open (one reply since the person spoke, to someone
else in the scene) and that the answer names exactly one candidate; anything else, a late answer or a failing
provider means no reaction.
"""
from __future__ import annotations

import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from app.observability.tts_stream_diagnostics import stream_log
from app.platform.chat.store import _model_key, _provider_key
from app.providers import ChatMessage as ProviderMessage
from app.providers import service as provider_service
from app.providers.catalog import LIVE_TURNS, provider_supports
from app.providers.lmstudio_provider import LMStudioProvider

from app.conversation.scene import speaking_as

from .scene import (
    ReactionOpening, Scene, SceneTalkKind, director_prompt, first_speaker_prompt, line_opening, load_scene,
    parse_director, reaction_opening, reaction_reason, talk_opening, talk_reason, thread_director_prompt, turn_scene,
)

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 4.0
# Who answers the person first is asked before their reply starts, so a slow answer falls back sooner.
_FIRST_SPEAKER_TIMEOUT_SECONDS = 2.5
# A name is a few words: an answer longer than this is not one.
_ANSWER_CHARS = 80


def _answer(chunks: Any) -> str:
    text = ""
    for chunk in chunks:
        text += str(getattr(chunk, "content", "") or "")
        if "\n" in text.strip() or len(text) > _ANSWER_CHARS:
            break
    return text.strip().splitlines()[0] if text.strip() else ""


def choose_reactor(session: Any, scene: Scene, opening: ReactionOpening) -> str | None:
    """The member who reacts, or None. Never raises: no reaction is always a safe answer."""
    return _ask_director(session, opening, director_prompt(scene, opening), "scene_reaction_directed")


def choose_talker(session: Any, scene: Scene, opening: ReactionOpening) -> str | None:
    """Who says a thread's next line or a talk opener (companion 6.4), or None. With one candidate there is
    nothing to choose: that member's own line model may still SKIP. With two, the thread director proposes a
    name, and code accepts only a listed candidate."""
    if len(opening.candidates) == 1:
        return opening.candidates[0].character_id
    return _ask_director(session, opening, thread_director_prompt(scene, opening), "scene_talk_directed")


def choose_first_speaker(session: Any, scene: Scene, opening: ReactionOpening) -> str | None:
    """Who answers the person first when they name no one (group calls, 2026-11-19), or None for the usual
    choice. The model proposes a name; code accepts only one of the members."""
    return _ask_director(session, opening, first_speaker_prompt(opening), "scene_first_speaker_directed",
                         timeout_seconds=_FIRST_SPEAKER_TIMEOUT_SECONDS)


def directed_turn_scene(session: Any, text: str) -> Scene | None:
    """``turn_scene`` with the call's model proposing who answers first."""
    return turn_scene(session, text, director=lambda scene, opening: choose_first_speaker(session, scene, opening))


def _ask_director(session: Any, opening: ReactionOpening, prompt: str, event: str, *,
                  timeout_seconds: float = _REQUEST_TIMEOUT_SECONDS) -> str | None:
    started = time.perf_counter()
    answer = ""
    reactor: str | None = None
    reason = "declined"
    try:
        provider = provider_service.get_provider(_provider_key(getattr(session, "provider_id", None)))
        if provider is None or not hasattr(provider, "chat_completion"):
            reason = "provider_unavailable"
        else:
            kwargs: dict[str, Any] = (
                {"live_turn": True}
                if provider_supports(provider, LIVE_TURNS)
                else {"chat_template_kwargs": {"enable_thinking": False}}
            )
            stream = provider.chat_completion(
                messages=[ProviderMessage(role="user", content=prompt)],
                model=None if isinstance(provider, LMStudioProvider) else _model_key(getattr(session, "model_id", None)),
                stream=True,
                request_timeout_seconds=timeout_seconds,
                **kwargs,
            )
            try:
                answer = _answer(stream)
            finally:
                close = getattr(stream, "close", None)
                if callable(close):
                    with suppress(Exception):
                        close()
            reactor = parse_director(opening, answer)
            reason = "chosen" if reactor else "declined"
    except Exception:  # noqa: BLE001 - a failed director call means nobody reacts
        logger.warning("scene director unavailable", exc_info=True)
        reason = "provider_failed"
    stream_log(
        "gateway-live-chat-scene",
        "runtime",
        event,
        session_id=getattr(session, "id", None),
        reason=reason,
        reactor=reactor,
        candidates=len(opening.candidates),
        elapsed_ms=round((time.perf_counter() - started) * 1000.0, 1),
    )
    return reactor


@dataclass(frozen=True)
class SceneReaction:
    """A reaction code allowed: its reason (naming the member), the opening, and that member's view."""

    reason: str
    speaker_id: str
    opening: ReactionOpening
    view: Any


def scene_reaction_opening(session: Any) -> tuple[Scene, ReactionOpening] | None:
    """The chat's scene and its open reaction, or None when no reaction may follow now."""
    scene = load_scene(session)
    opening = reaction_opening(scene, session.messages) if scene is not None else None
    return (scene, opening) if scene is not None and opening is not None else None


def direct_scene_reaction(session: Any, scene: Scene, opening: ReactionOpening) -> SceneReaction | None:
    """Ask who reacts; the reaction is generated from that member's read-only view of the session."""
    reactor = choose_reactor(session, scene, opening)
    if reactor is None:
        return None
    return SceneReaction(reason=reaction_reason(reactor), speaker_id=reactor, opening=opening,
                         view=speaking_as(session, scene.with_speaker(reactor)))


def scene_talk_opening(session: Any, kind: SceneTalkKind, *, max_lines: int) -> tuple[Scene, ReactionOpening] | None:
    """The chat's scene and the opening a further line (``line``) or an opener (``talk``) would follow, or None."""
    scene = load_scene(session)
    if scene is None:
        return None
    opening = (line_opening(scene, session.messages, max_lines=max_lines) if kind == "line"
               else talk_opening(scene, session.messages))
    return (scene, opening) if opening is not None else None


def direct_scene_talk(session: Any, scene: Scene, opening: ReactionOpening, kind: SceneTalkKind) -> SceneReaction | None:
    """Choose who speaks a line or an opener; it is generated from that member's read-only view of the session."""
    speaker = choose_talker(session, scene, opening)
    if speaker is None:
        return None
    return SceneReaction(reason=talk_reason(kind, speaker), speaker_id=speaker, opening=opening,
                         view=speaking_as(session, scene.with_speaker(speaker)))


__all__ = [
    "SceneReaction",
    "choose_first_speaker",
    "choose_reactor",
    "choose_talker",
    "direct_scene_reaction",
    "direct_scene_talk",
    "directed_turn_scene",
    "scene_reaction_opening",
    "scene_talk_opening",
]
