"""Story auto-generation hooks."""
from __future__ import annotations

from typing import Any, Dict

from app.image.service import enqueue_story_image


def maybe_enqueue_story_scene_image(*, session_id: str, story_text: str, settings: Dict[str, Any] | None = None):
    settings = settings or {}
    if not bool(settings.get("auto_generate_scene_images", False)):
        return {"ok": False, "reason": "disabled"}

    prompt = story_text.strip()
    if not prompt:
        return {"ok": False, "reason": "empty_prompt"}

    return enqueue_story_image({
        "session_id": session_id,
        "request_id": f"story_scene:{session_id}",
        "prompt": prompt,
        "kind": "scene",
        "style": settings.get("style", "story"),
        "metadata": {
            "trigger": "story_scene_auto",
        },
    })


def maybe_enqueue_story_cover_image(*, session_id: str, cover_prompt: str, settings: Dict[str, Any] | None = None):
    settings = settings or {}
    if not bool(settings.get("auto_generate_cover_images", False)):
        return {"ok": False, "reason": "disabled"}

    prompt = cover_prompt.strip()
    if not prompt:
        return {"ok": False, "reason": "empty_prompt"}

    return enqueue_story_image({
        "session_id": session_id,
        "request_id": f"story_cover:{session_id}",
        "prompt": prompt,
        "kind": "cover",
        "style": settings.get("style", "story_cover"),
        "metadata": {
            "trigger": "story_cover_auto",
        },
    })
