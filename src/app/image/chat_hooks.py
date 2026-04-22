"""Chat auto-generation hooks."""
from __future__ import annotations

from typing import Any, Dict

from app.image.service import enqueue_chat_image


def maybe_enqueue_chat_image(*, session_id: str, user_text: str, assistant_text: str, settings: Dict[str, Any] | None = None):
    settings = settings or {}
    if not bool(settings.get("auto_generate_images", False)):
        return {"ok": False, "reason": "disabled"}

    prompt = assistant_text.strip() or user_text.strip()
    if not prompt:
        return {"ok": False, "reason": "empty_prompt"}

    return enqueue_chat_image({
        "session_id": session_id,
        "request_id": f"chat:{session_id}",
        "prompt": prompt,
        "kind": "image",
        "style": settings.get("style", ""),
        "metadata": {
            "trigger": "chat_auto",
        },
    })
