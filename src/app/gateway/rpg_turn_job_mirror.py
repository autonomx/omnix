"""Mirror direct foreground RPG turns into the durable job store."""
from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, Request

_DIRECT_RPG_TURN_ACTIVE: ContextVar[bool] = ContextVar("omnix_direct_rpg_turn_active", default=False)
_HOOK_SENTINEL = "_omnix_rpg_turn_job_mirror_hook_installed"
_MIDDLEWARE_SENTINEL = "_omnix_rpg_turn_job_mirror_middleware_installed"


def install_rpg_turn_job_mirror_hook() -> None:
    """Install direct-route job mirroring for the web gateway.

    The direct foreground turn route bypasses the shared `/api/jobs` submission
    path so the UI can render immediately. This hook preserves observability by
    mirroring only requests to `/api/rpg/sessions/{session_id}/turn` into the
    normal durable job store as completed `rpg.turn` records.
    """

    _install_apply_turn_wrapper()
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return

    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            _install_middleware(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)


def _install_middleware(app: FastAPI) -> None:
    if getattr(app.state, _MIDDLEWARE_SENTINEL, False):
        return
    setattr(app.state, _MIDDLEWARE_SENTINEL, True)

    @app.middleware("http")
    async def mirror_direct_rpg_turns(request: Request, call_next: Callable[..., Any]) -> Any:
        if request.method.upper() == "POST" and _is_direct_turn_path(request.url.path):
            token = _DIRECT_RPG_TURN_ACTIVE.set(True)
            try:
                return await call_next(request)
            finally:
                _DIRECT_RPG_TURN_ACTIVE.reset(token)
        return await call_next(request)


def _is_direct_turn_path(path: str) -> bool:
    parts = [part for part in path.split("/") if part]
    return len(parts) == 5 and parts[0] == "api" and parts[1] == "rpg" and parts[2] == "sessions" and parts[4] == "turn"


def _install_apply_turn_wrapper() -> None:
    from app.rpg.session import interactive_first_call_runtime

    if getattr(interactive_first_call_runtime, "_omnix_rpg_turn_job_mirror_installed", False):
        return

    original_apply_turn = interactive_first_call_runtime.apply_turn

    @wraps(original_apply_turn)
    def mirrored_apply_turn(session_id: str, command: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if not _DIRECT_RPG_TURN_ACTIVE.get(False):
            return original_apply_turn(session_id, command, *args, **kwargs)
        return _apply_turn_with_job_mirror(original_apply_turn, session_id, command, *args, **kwargs)

    interactive_first_call_runtime.apply_turn = mirrored_apply_turn
    interactive_first_call_runtime._omnix_rpg_turn_job_mirror_installed = True


def _apply_turn_with_job_mirror(
    apply_turn: Callable[..., dict[str, Any]],
    session_id: str,
    command: str,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    from app.jobs.models import CompleteJobRequest, CreateJobRequest, FailJobRequest, ResourceClass
    from app.jobs.store import default_job_store

    store = default_job_store()
    job = store.create_job(
        CreateJobRequest(
            module="rpg",
            type="rpg.turn",
            resource_class=ResourceClass.GPU_LLM,
            priority=0,
            input_ref={"session_id": session_id},
            input_payload={
                "command": command,
                "player_input": command,
                "determinism_policy": "replay_preserving",
                "source": "direct_foreground_route",
            },
            compat={"direct_foreground_route": True, "synthetic_job_mirror": True},
        )
    )
    running = store.mark_running(job.id) or job

    try:
        result = apply_turn(session_id, command, *args, **kwargs)
    except Exception as exc:
        store.fail_job(
            running.id,
            FailJobRequest(
                code="direct_rpg_turn_failed",
                message=str(exc) or "Direct RPG turn failed",
                retryable=False,
                details={"session_id": session_id, "command": command},
            ),
        )
        raise

    if result.get("ok") is not True:
        error = str(result.get("error") or "direct_rpg_turn_failed")
        store.fail_job(
            running.id,
            FailJobRequest(
                code=error,
                message=error,
                retryable=False,
                details={"session_id": session_id, "command": command, "result": result},
            ),
        )
        return result

    content = _visible_turn_text(result, command)
    completed = store.complete_job(
        running.id,
        CompleteJobRequest(
            output_refs=[
                {
                    "type": "rpg_turn_response",
                    "module": "rpg",
                    "title": command[:80] or "RPG turn",
                    "content": content,
                    "session_id": session_id,
                    "command": command,
                    "raw_turn_result": result,
                    "result": result,
                    "source": "direct_foreground_route",
                }
            ],
            logs=[
                {
                    "level": "info",
                    "message": "RPG turn applied by direct foreground route",
                    "content": content,
                    "session_id": session_id,
                    "command": command,
                }
            ],
        ),
    )
    if completed is not None:
        job_payload = completed.model_dump(mode="json")
        result["foreground_job"] = job_payload
        result["creation_server_trace"] = {
            "server_job_created_at": completed.created_at,
            "server_job_started_at": completed.started_at,
            "server_job_completed_at": completed.completed_at,
            "server_response_persisted_at": completed.completed_at,
            "job_id": completed.id,
        }
    return result


def _visible_turn_text(result: dict[str, Any], command: str) -> str:
    for key in ("final_narration", "narration", "summary", "response", "content"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = result.get("result")
    if isinstance(nested, dict):
        return _visible_turn_text(nested, command)
    authoritative = result.get("authoritative")
    if isinstance(authoritative, dict):
        return _visible_turn_text(authoritative, command)
    return f"Your command is accepted: {command}."
