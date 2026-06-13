"""Omnix Python startup compatibility hooks.

This module is imported automatically by Python when ``src`` is on the
interpreter path, which is the case for the local launch scripts. Keep this
file intentionally tiny and deterministic.
"""

from __future__ import annotations

import builtins
from typing import Any, Dict, Iterator


# Older/newer NPC initiative slices disagree on where ``opening_bonus`` is
# defined. The initiative module reads it as a global fallback in one idle
# candidate path; providing a builtins default prevents resume/idle catch-up
# from crashing while the owning module is normalized.
if not hasattr(builtins, "opening_bonus"):
    builtins.opening_bonus = 0.0


def _install_rpg_lmstudio_gateway_compat() -> None:
    """Let RPG narrator paths call LMStudioProvider like AppLLMGateway.

    Some legacy narration code is passed the active provider directly instead
    of the RPG AppLLMGateway adapter. The provider exposes ``chat_completion``;
    the narrator expects ``generate`` / ``generate_stream`` / ``call``. Add those
    adapter methods once at startup so those paths produce text instead of
    ``AttributeError('gateway has no generate or call interface')``.
    """

    try:
        from app.providers.base import ChatMessage, ChatResponse
        from app.providers.lmstudio_provider import LMStudioProvider
    except Exception:
        return

    if not hasattr(LMStudioProvider, "generate"):
        def generate(self: Any, prompt: str, *, context: Dict[str, Any] | None = None, **kwargs: Any) -> str:
            messages = [
                ChatMessage(
                    role="system",
                    content=(
                        "You are a deterministic RPG narration engine. "
                        "Return concise player-facing RPG narration or NPC dialogue."
                    ),
                ),
                ChatMessage(role="user", content=str(prompt or "")),
            ]
            if context:
                messages.append(ChatMessage(role="user", content="Context JSON:\n" + str(context)))
            response = self.chat_completion(messages=messages, stream=False, **kwargs)
            if isinstance(response, ChatResponse):
                return str(response.content or "").strip()
            return str(response or "").strip()

        LMStudioProvider.generate = generate  # type: ignore[attr-defined]

    if not hasattr(LMStudioProvider, "generate_stream"):
        def generate_stream(self: Any, prompt: str, *, context: Dict[str, Any] | None = None, **kwargs: Any) -> Iterator[Dict[str, str]]:
            messages = [
                ChatMessage(
                    role="system",
                    content=(
                        "You are a deterministic RPG narration engine. "
                        "Return concise player-facing RPG narration or NPC dialogue."
                    ),
                ),
                ChatMessage(role="user", content=str(prompt or "")),
            ]
            if context:
                messages.append(ChatMessage(role="user", content="Context JSON:\n" + str(context)))
            for chunk in self.chat_completion(messages=messages, stream=True, **kwargs):
                text = str(getattr(chunk, "content", "") or "")
                if text:
                    yield {"text": text}

        LMStudioProvider.generate_stream = generate_stream  # type: ignore[attr-defined]

    if not hasattr(LMStudioProvider, "call"):
        def call(self: Any, method: str, prompt: str, *, context: Dict[str, Any] | None = None, **kwargs: Any) -> Any:
            if method == "generate":
                return self.generate(prompt, context=context, **kwargs)
            if method == "generate_stream":
                return self.generate_stream(prompt, context=context, **kwargs)
            raise ValueError(f"Unsupported RPG provider method: {method}")

        LMStudioProvider.call = call  # type: ignore[attr-defined]


_install_rpg_lmstudio_gateway_compat()
