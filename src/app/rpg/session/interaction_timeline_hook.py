"""Install durable interaction progression at the interactive turn boundary."""
from __future__ import annotations

import threading
from functools import wraps
from typing import Any, Callable

from .interaction_event_store import (
    append_interaction_event,
    compact_interaction_event_log,
    interaction_event_log_status,
    interaction_log_requires_compaction,
)
from .interaction_timeline import commit_turn_interaction, mark_interaction_persisted

_SENTINEL = "_omnix_interaction_timeline_hook_installed"
_SESSION_LOCKS: dict[str, threading.RLock] = {}
_SESSION_LOCKS_GUARD = threading.RLock()


def install_interaction_timeline_hook() -> None:
    from app.rpg.session import interactive_first_call_runtime

    if getattr(interactive_first_call_runtime, _SENTINEL, False):
        return

    original_apply_turn: Callable[..., dict[str, Any]] = interactive_first_call_runtime.apply_turn

    @wraps(original_apply_turn)
    def apply_turn_with_interaction_timeline(
        session_id: str,
        player_input: str,
        action: dict[str, Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        with _session_lock(session_id):
            result = original_apply_turn(session_id, player_input, action, *args, **kwargs)
            if not isinstance(result, dict) or result.get("ok") is not True:
                return result
            if result.get("interaction_persisted") is True:
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

            session, result, event = commit_turn_interaction(
                session,
                result,
                player_input=player_input,
                submission_id=_current_submission_id(),
                trace_id=_text(result.get("trace_id")),
            )
            result["session"] = session
            if isinstance(session_override, dict):
                session_override.clear()
                session_override.update(session)
                result["interaction_persisted"] = False
                result["interaction_persistence"] = {
                    "format_version": "rpg_interaction_persistence_v2",
                    "mode": "session_override",
                    "persisted": False,
                }
                return result

            append_interaction_event(session_id, event)
            snapshot_required = event.get("stateful") is not False or interaction_log_requires_compaction(session_id)
            persistence_mode = "event_log"
            if snapshot_required:
                from .service import save_session

                saved = save_session(session, compact=True)
                result["session"] = saved
                compact_interaction_event_log(
                    session_id,
                    through_sequence=int(event.get("sequence") or 0),
                )
                persistence_mode = "snapshot_compacted"

            mark_interaction_persisted(result)
            result["interaction_persistence"] = {
                "format_version": "rpg_interaction_persistence_v2",
                "interaction_id": event.get("interaction_id"),
                "sequence": event.get("sequence"),
                "state_revision": event.get("state_revision"),
                "persisted": True,
                "mode": persistence_mode,
                "snapshot_written": snapshot_required,
                "event_log": interaction_event_log_status(session_id),
            }
            return result

    interactive_first_call_runtime.apply_turn = apply_turn_with_interaction_timeline
    setattr(interactive_first_call_runtime, _SENTINEL, True)


def _session_lock(session_id: str) -> threading.RLock:
    key = _text(session_id) or "session"
    with _SESSION_LOCKS_GUARD:
        lock = _SESSION_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _SESSION_LOCKS[key] = lock
        return lock


def _current_submission_id() -> str:
    try:
        from app.gateway.rpg_turn_job_mirror import _DIRECT_RPG_SUBMISSION_ID

        return _text(_DIRECT_RPG_SUBMISSION_ID.get(""))
    except Exception:
        return ""


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
