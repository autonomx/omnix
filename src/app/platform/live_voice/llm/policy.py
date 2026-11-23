"""Provider options selected for a live voice turn."""
from __future__ import annotations

from app.conversation.contracts import is_live_voice_message
from typing import Any


def lmstudio_live_voice_options(user_message: Any) -> dict[str, Any]:
    """Disable chain-of-thought output for spoken turns on LM Studio."""
    if not is_live_voice_message(user_message):
        return {}
    return {"chat_template_kwargs": {"enable_thinking": False}}


__all__ = ["is_live_voice_message", "lmstudio_live_voice_options"]
