"""Install durable interaction progression at the interactive turn boundary."""
from __future__ import annotations

import threading
from functools import wraps
from typing import Any, Callable

from app.rpg.narrative_engine.persistence_policy import (
    narrative_repository_save_policy,
)
from app.persistence.rpg_session_save_policy import rpg_session_save_policy
from app.rpg.performance_trace import rpg_pipeline_span

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
        lock = _session_lock(session_id)
        with rpg_pipeline_span("turn.session_lock_wait", fields={"session_id": session_id}):
            lock.acquire()
        try:
            postgres_active = _postgresql_runtime_active()
            with (
                narrative_repository_save_policy(defer=postgres_active),
                rpg_session_save_policy(defer=postgres_active),
            ):
                with rpg_pipeline_span("turn.runtime_resolution") as runtime_span:
                    result = original_apply_turn(session_id, player_input, action, *args, **kwargs)
                    runtime_span["ok"] = result.get("ok") is True if isinstance(result, dict) else False
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

                submission_id = _current_submission_id()
                with rpg_pipeline_span("turn.interaction_append") as interaction_span:
                    session, result, event = commit_turn_interaction(
                        session,
                        result,
                        player_input=player_input,
                        submission_id=submission_id,
                        trace_id=_text(result.get("trace_id")),
                    )
                    interaction_span["interaction_id"] = event.get("interaction_id")
                    interaction_span["sequence"] = event.get("sequence")
                    interaction_span["stateful"] = event.get("stateful")
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

                if postgres_active:
                    from app.persistence.rpg_turn_service import persist_foreground_turn
                    from app.rpg.session.narrative_engine_bridge import (
                        canonicalize_resolved_turn_result,
                    )

                    with rpg_pipeline_span("turn.canonical_before_commit") as narrative_span:
                        result = canonicalize_resolved_turn_result(
                            result,
                            session_id=session_id,
                            player_input=player_input,
                        )
                        canonical = result.get("canonical_narrative_response")
                        narrative_span["response_id"] = (
                            canonical.get("response_id")
                            if isinstance(canonical, dict)
                            else None
                        )
                        narrative_span["content_hash"] = (
                            canonical.get("content_hash")
                            if isinstance(canonical, dict)
                            else None
                        )
                    result["session"] = session
                    with rpg_pipeline_span("turn.postgresql_commit") as transaction_span:
                        transaction = persist_foreground_turn(
                            session_id=session_id,
                            player_input=player_input,
                            session=session,
                            result=result,
                            event=event,
                            submission_id=submission_id,
                        )
                        transaction_span["interaction_id"] = event.get("interaction_id")
                        transaction_span["sequence"] = event.get("sequence")
                        transaction_span["submission_id"] = submission_id
                        transaction_span["narrative_response_id"] = transaction.get(
                            "narrative_response_id"
                        )
                    mark_interaction_persisted(result)
                    result["interaction_persistence"] = {
                        "format_version": "rpg_interaction_persistence_v4",
                        "interaction_id": event.get("interaction_id"),
                        "sequence": event.get("sequence"),
                        "state_revision": event.get("state_revision"),
                        "submission_id": submission_id,
                        "persisted": True,
                        "mode": "postgresql_unit_of_work",
                        "snapshot_written": transaction.get("snapshot") is not None,
                        "turn_id": (transaction.get("turn") or {}).get("id"),
                        "job_id": (transaction.get("job") or {}).get("id"),
                        "narrative_response_id": transaction.get("narrative_response_id"),
                        "narrative_content_hash": transaction.get("narrative_content_hash"),
                        "narrative_atomic_with_turn": transaction.get(
                            "narrative_atomic_with_turn"
                        )
                        is True,
                    }
                    return result

                with rpg_pipeline_span("turn.interaction_event_write") as event_span:
                    append_interaction_event(session_id, event)
                    event_span["sequence"] = event.get("sequence")
                snapshot_required = event.get("stateful") is not False or interaction_log_requires_compaction(session_id)
                persistence_mode = "event_log"
                if snapshot_required:
                    from .service import save_session

                    with rpg_pipeline_span("turn.session_snapshot_write") as snapshot_span:
                        saved = save_session(session, compact=True)
                        snapshot_span["sequence"] = event.get("sequence")
                        snapshot_span["stateful"] = event.get("stateful")
                    result["session"] = saved
                    with rpg_pipeline_span("turn.interaction_log_compaction") as compact_span:
                        compact_interaction_event_log(
                            session_id,
                            through_sequence=int(event.get("sequence") or 0),
                        )
                        compact_span["through_sequence"] = event.get("sequence")
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
        finally:
            lock.release()

    interactive_first_call_runtime.apply_turn = apply_turn_with_interaction_timeline
    setattr(interactive_first_call_runtime, _SENTINEL, True)


def _postgresql_runtime_active() -> bool:
    try:
        from app.persistence.runtime_install import runtime_adapters_installed

        return runtime_adapters_installed()
    except Exception:
        return False


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
