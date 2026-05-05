from __future__ import annotations

from typing import Any

from app.rpg.session.deferred_narration_guard import suppress_provider_runtime_narration


def get_runtime_llm_provider() -> Any:
    if suppress_provider_runtime_narration():
        return None
    """Return the centralized app LLM provider if available.

    Keep this tiny and defensive so tests can monkeypatch it easily.
    """
    try:
        from app import shared  # type: ignore

        getter = getattr(shared, "get_provider", None)
        if callable(getter):
            return getter()
    except Exception:
        return None
    return None