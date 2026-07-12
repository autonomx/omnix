from __future__ import annotations

from functools import wraps
from time import perf_counter
from typing import Any, Callable

from app.rpg.debug_logging import (
    configure_rpg_debug_logging,
    log_rpg_event,
    new_rpg_trace_id,
    summarize_turn_result,
)

_SENTINEL = "_omnix_rpg_runtime_debug_hook_installed"


def install_rpg_runtime_debug_hook() -> None:
    """Wrap the interactive turn boundary with durable structured diagnostics."""

    from app.rpg.session import interactive_first_call_runtime

    if getattr(interactive_first_call_runtime, _SENTINEL, False):
        return

    configure_rpg_debug_logging()
    original_apply_turn: Callable[..., dict[str, Any]] = interactive_first_call_runtime.apply_turn

    @wraps(original_apply_turn)
    def logged_apply_turn(
        session_id: str,
        player_input: str,
        action: dict[str, Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        trace_id = new_rpg_trace_id("turn")
        started_at = perf_counter()
        performance_override = kwargs.get("performance_override")
        session_override = kwargs.get("session_override")
        log_rpg_event(
            "turn.started",
            category="performance",
            session_id=session_id,
            trace_id=trace_id,
            fields={
                "player_input": player_input,
                "player_input_chars": len(str(player_input or "")),
                "action": action or {},
                "performance_override": performance_override or {},
                "session_override_present": isinstance(session_override, dict),
            },
        )
        try:
            result = original_apply_turn(session_id, player_input, action, *args, **kwargs)
        except Exception as exc:
            log_rpg_event(
                "turn.exception",
                category="performance",
                level="error",
                session_id=session_id,
                trace_id=trace_id,
                duration_ms=(perf_counter() - started_at) * 1000.0,
                fields={
                    "player_input": player_input,
                    "action": action or {},
                    "performance_override": performance_override or {},
                },
                error=exc,
                include_traceback=True,
            )
            raise

        summary = summarize_turn_result(result)
        turn_id = str(summary.get("turn_id") or "") or None
        ok = result.get("ok") is True if isinstance(result, dict) else False
        log_rpg_event(
            "turn.completed" if ok else "turn.failed",
            category="performance",
            level="info" if ok else "error",
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            duration_ms=(perf_counter() - started_at) * 1000.0,
            fields={
                "player_input": player_input,
                "result": summary,
            },
            error=str(result.get("error")) if isinstance(result, dict) and result.get("error") else None,
        )
        return result

    interactive_first_call_runtime.apply_turn = logged_apply_turn
    setattr(interactive_first_call_runtime, _SENTINEL, True)
