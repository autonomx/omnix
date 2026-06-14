from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_common import d, s
from app.rpg.session.turn_memory_context import attach_turn_memory_context_with_session
from app.rpg.session.turn_memory_runtime_persistence import select_memory_session
from app.rpg.session.turn_memory_runtime_session_store import save_persisted_session
from app.rpg.session.turn_memory_runtime_status import attach_hook_status


def attach_turn_memory_to_runtime_result(
    result: dict[str, Any],
    *,
    call_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach deterministic recent/dialogue memory to an interactive turn result."""

    if not isinstance(result, dict):
        return result
    context = d(call_context)
    try:
        session, can_persist = select_memory_session(result, context)
        updated_result, updated_session = attach_turn_memory_context_with_session(
            result,
            session=session,
            player_input=s(context.get("player_input")),
        )
        persisted = save_persisted_session(
            updated_session,
            session_id=s(context.get("session_id")),
        ) if can_persist else False
        return attach_hook_status(updated_result, attached=True, persisted=persisted)
    except Exception as exc:
        return attach_hook_status(result, attached=False, error=f"{type(exc).__name__}: {exc}")
