"""Bind authoritative turns and deferred narration workers to one interaction."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from .interaction_lifecycle import (
    apply_narration_result_to_interaction,
    initialize_interaction_lifecycle,
    queue_deferred_narration_for_interaction,
    recover_pending_interaction_narration,
)

_RUNTIME_SENTINEL = "_omnix_interaction_lifecycle_runtime_hook_installed"
_WORKER_SENTINEL = "_omnix_interaction_lifecycle_worker_hook_installed"
_LOAD_SENTINEL = "_omnix_interaction_lifecycle_load_hook_installed"


def install_interaction_lifecycle_hook() -> None:
    _install_runtime_hook()
    _install_worker_hook()
    _install_load_recovery_hook()


def _install_runtime_hook() -> None:
    from app.rpg.session import interactive_first_call_runtime

    if getattr(interactive_first_call_runtime, _RUNTIME_SENTINEL, False):
        return
    original: Callable[..., dict[str, Any]] = interactive_first_call_runtime.apply_turn

    @wraps(original)
    def apply_turn_with_lifecycle(
        session_id: str,
        player_input: str,
        action: dict[str, Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        result = original(session_id, player_input, action, *args, **kwargs)
        if not isinstance(result, dict) or result.get("ok") is not True:
            return result
        session = result.get("session")
        session_override = kwargs.get("session_override")
        if not isinstance(session, dict) and isinstance(session_override, dict):
            session = session_override
        if not isinstance(session, dict):
            from .service import load_session

            session = load_session(session_id)
        if not isinstance(session, dict):
            return result

        lifecycle = initialize_interaction_lifecycle(session, result)
        result["session"] = session
        if isinstance(session_override, dict):
            session_override.clear()
            session_override.update(session)
        if lifecycle.get("status") == "narration_pending":
            try:
                queue_deferred_narration_for_interaction(session_id, result)
            except Exception:
                # Authoritative result remains valid even when enrichment cannot queue.
                result["narration_status"] = "failed_to_queue"
        return result

    interactive_first_call_runtime.apply_turn = apply_turn_with_lifecycle
    setattr(interactive_first_call_runtime, _RUNTIME_SENTINEL, True)


def _install_worker_hook() -> None:
    from app.rpg.session import runtime

    if getattr(runtime, _WORKER_SENTINEL, False):
        return
    original: Callable[[str], dict[str, Any]] = runtime.process_next_narration_job

    @wraps(original)
    def process_next_with_lifecycle(session_id: str) -> dict[str, Any]:
        result = original(session_id)
        if not isinstance(result, dict):
            return result
        try:
            return apply_narration_result_to_interaction(session_id, result)
        except Exception:
            return result

    runtime.process_next_narration_job = process_next_with_lifecycle
    setattr(runtime, _WORKER_SENTINEL, True)


def _install_load_recovery_hook() -> None:
    from app.rpg.session import service

    if getattr(service, _LOAD_SENTINEL, False):
        return
    original: Callable[..., Any] = service.load_session

    @wraps(original)
    def load_session_with_pending_recovery(session_id: str, *args: Any, **kwargs: Any) -> Any:
        session = original(session_id, *args, **kwargs)
        if isinstance(session, dict):
            try:
                recover_pending_interaction_narration(session_id, session)
            except Exception:
                pass
        return session

    service.load_session = load_session_with_pending_recovery
    setattr(service, _LOAD_SENTINEL, True)
