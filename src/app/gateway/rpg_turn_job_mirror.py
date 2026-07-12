"""Record direct foreground RPG turns without scheduling a second execution."""
from __future__ import annotations

import os
import threading
import uuid
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, Request

from app.jobs.rpg_turn_job_guard import RPG_FOREGROUND_RECORD_TYPE

_DIRECT_RPG_TURN_ACTIVE: ContextVar[bool] = ContextVar("omnix_direct_rpg_turn_active", default=False)
_DIRECT_RPG_SUBMISSION_ID: ContextVar[str] = ContextVar("omnix_direct_rpg_submission_id", default="")
_HOOK_SENTINEL = "_omnix_rpg_turn_job_mirror_hook_installed"
_MIDDLEWARE_SENTINEL = "_omnix_rpg_turn_job_mirror_middleware_installed"
_SUBMISSION_LOCKS: dict[str, threading.RLock] = {}
_SUBMISSION_LOCKS_GUARD = threading.RLock()


def install_rpg_turn_job_mirror_hook() -> None:
    """Install record-only job mirroring for the direct web turn route."""

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
            active_token = _DIRECT_RPG_TURN_ACTIVE.set(True)
            submission_id = request.headers.get("x-omnix-rpg-submission-id", "").strip() or f"submit:{uuid.uuid4().hex}"
            submission_token = _DIRECT_RPG_SUBMISSION_ID.set(submission_id)
            try:
                response = await call_next(request)
                response.headers["X-Omnix-Rpg-Submission-Id"] = submission_id
                return response
            finally:
                _DIRECT_RPG_SUBMISSION_ID.reset(submission_token)
                _DIRECT_RPG_TURN_ACTIVE.reset(active_token)
        return await call_next(request)


def _is_direct_turn_path(path: str) -> bool:
    parts = [part for part in path.split("/") if part]
    return len(parts) == 5 and parts[:3] == ["api", "rpg", "sessions"] and parts[4] == "turn"


def _install_apply_turn_wrapper() -> None:
    from app.rpg.session import interactive_first_call_runtime

    if getattr(interactive_first_call_runtime, "_omnix_rpg_turn_job_mirror_installed", False):
        return

    original_apply_turn = interactive_first_call_runtime.apply_turn

    @wraps(original_apply_turn)
    def mirrored_apply_turn(session_id: str, command: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if not _DIRECT_RPG_TURN_ACTIVE.get(False):
            return original_apply_turn(session_id, command, *args, **kwargs)
        return _apply_turn_with_job_mirror(
            original_apply_turn,
            session_id,
            command,
            *args,
            submission_id=_DIRECT_RPG_SUBMISSION_ID.get("") or None,
            **kwargs,
        )

    interactive_first_call_runtime.apply_turn = mirrored_apply_turn
    interactive_first_call_runtime._omnix_rpg_turn_job_mirror_installed = True


def _apply_turn_with_job_mirror(
    apply_turn: Callable[..., dict[str, Any]],
    session_id: str,
    command: str,
    *args: Any,
    submission_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from app.jobs.models import CompleteJobRequest, CreateJobRequest, FailJobRequest, JobStatus, ResourceClass
    from app.jobs.rpg_foreground_submission_store import submission_store_for_job_store
    from app.jobs.store import default_job_store

    resolved_submission_id = str(submission_id or f"submit:{uuid.uuid4().hex}").strip()
    with _submission_lock(resolved_submission_id):
        store = default_job_store()
        durable_store = submission_store_for_job_store(store)
        durable_claim = durable_store.claim(session_id, resolved_submission_id) if durable_store is not None else None
        if durable_claim is not None and not durable_claim.owner:
            return _wait_for_durable_result(
                durable_store,
                durable_claim,
                session_id=session_id,
                submission_id=resolved_submission_id,
            )

        existing = _find_submission_record(store, session_id, resolved_submission_id)
        recovered = _recover_completed_result(existing)
        if recovered is not None:
            _complete_durable_claim(durable_store, durable_claim, recovered)
            return recovered

        job = store.create_job(
            CreateJobRequest(
                module="rpg",
                type=RPG_FOREGROUND_RECORD_TYPE,
                resource_class=ResourceClass.CPU,
                priority=0,
                input_ref={"session_id": session_id},
                input_payload={
                    "command": command,
                    "player_input": command,
                    "submission_id": resolved_submission_id,
                    "determinism_policy": "replay_preserving",
                    "source": "direct_foreground_route",
                },
                compat={
                    "direct_foreground_route": True,
                    "synthetic_job_mirror": True,
                    "record_only": True,
                },
            )
        )
        if durable_store is not None and durable_claim is not None and durable_claim.claim_token:
            durable_store.attach_job(
                session_id,
                resolved_submission_id,
                durable_claim.claim_token,
                job.id,
            )
        if job.status == JobStatus.COMPLETED:
            recovered = _recover_completed_result(job)
            if recovered is not None:
                _complete_durable_claim(durable_store, durable_claim, recovered)
                return recovered
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
                    details={
                        "session_id": session_id,
                        "submission_id": resolved_submission_id,
                        "command": command,
                    },
                ),
            )
            _fail_durable_claim(durable_store, durable_claim, str(exc) or "Direct RPG turn failed")
            raise

        if result.get("ok") is not True:
            error = str(result.get("error") or "direct_rpg_turn_failed")
            store.fail_job(
                running.id,
                FailJobRequest(
                    code=error,
                    message=error,
                    retryable=False,
                    details={
                        "session_id": session_id,
                        "submission_id": resolved_submission_id,
                        "command": command,
                    },
                ),
            )
            finalized = dict(result)
            finalized["submission_id"] = resolved_submission_id
            _complete_durable_claim(durable_store, durable_claim, finalized)
            return finalized

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
                        "submission_id": resolved_submission_id,
                        "command": command,
                        "raw_turn_result": result,
                        "source": "direct_foreground_route",
                    }
                ],
                logs=[
                    {
                        "level": "info",
                        "message": "RPG turn recorded by direct foreground route",
                        "content": content,
                        "session_id": session_id,
                        "submission_id": resolved_submission_id,
                    }
                ],
            ),
        )
        result = dict(result)
        result["submission_id"] = resolved_submission_id
        if completed is not None:
            result["foreground_job"] = completed.model_dump(mode="json")
            result["creation_server_trace"] = {
                "server_job_created_at": completed.created_at,
                "server_job_started_at": completed.started_at,
                "server_job_completed_at": completed.completed_at,
                "server_response_persisted_at": completed.completed_at,
                "job_id": completed.id,
                "submission_id": resolved_submission_id,
            }
        _complete_durable_claim(durable_store, durable_claim, result)
        return result


def _submission_lock(submission_id: str) -> threading.RLock:
    with _SUBMISSION_LOCKS_GUARD:
        lock = _SUBMISSION_LOCKS.get(submission_id)
        if lock is None:
            lock = threading.RLock()
            _SUBMISSION_LOCKS[submission_id] = lock
        return lock


def _find_submission_record(store: Any, session_id: str, submission_id: str) -> Any | None:
    try:
        jobs = store.list_jobs()
    except Exception:
        return None
    for job in jobs:
        if getattr(job, "type", "") != RPG_FOREGROUND_RECORD_TYPE:
            continue
        input_ref = getattr(job, "input_ref", None)
        payload = getattr(job, "input_payload", None)
        if not isinstance(input_ref, dict) or not isinstance(payload, dict):
            continue
        if str(input_ref.get("session_id") or "") != session_id:
            continue
        if str(payload.get("submission_id") or "") == submission_id:
            return job
    return None


def _recover_completed_result(job: Any | None) -> dict[str, Any] | None:
    if job is None or str(getattr(getattr(job, "status", None), "value", getattr(job, "status", ""))) != "completed":
        return None
    output_refs = getattr(job, "output_refs", None)
    if not isinstance(output_refs, list) or not output_refs:
        return None
    first = output_refs[0] if isinstance(output_refs[0], dict) else {}
    raw = first.get("raw_turn_result")
    if not isinstance(raw, dict):
        return None
    recovered = deepcopy(raw)
    submission_id = str(first.get("submission_id") or "")
    recovered["submission_id"] = submission_id
    recovered["foreground_job"] = job.model_dump(mode="json")
    recovered["idempotent_replay"] = True
    return recovered


def _wait_for_durable_result(
    durable_store: Any,
    claim: Any,
    *,
    session_id: str,
    submission_id: str,
) -> dict[str, Any]:
    immediate = _recover_durable_result(claim)
    if immediate is not None:
        return immediate
    terminal = durable_store.wait_for_terminal(
        session_id,
        submission_id,
        timeout_seconds=_submission_wait_seconds(),
    )
    recovered = _recover_durable_result(terminal)
    if recovered is not None:
        return recovered
    if getattr(terminal, "status", "") == "failed":
        raise RuntimeError(getattr(terminal, "error", None) or "foreground submission failed")
    raise TimeoutError(
        f"foreground submission {submission_id} for {session_id} did not reach a terminal state"
    )


def _recover_durable_result(claim: Any) -> dict[str, Any] | None:
    if getattr(claim, "status", "") != "completed":
        return None
    raw = getattr(claim, "result", None)
    if not isinstance(raw, dict):
        return None
    recovered = deepcopy(raw)
    recovered["submission_id"] = str(getattr(claim, "submission_id", "") or recovered.get("submission_id") or "")
    recovered["idempotent_replay"] = True
    return recovered


def _complete_durable_claim(durable_store: Any, claim: Any, result: dict[str, Any]) -> None:
    token = getattr(claim, "claim_token", None)
    if durable_store is None or not token:
        return
    durable_store.complete(claim.session_id, claim.submission_id, token, result)


def _fail_durable_claim(durable_store: Any, claim: Any, error: str) -> None:
    token = getattr(claim, "claim_token", None)
    if durable_store is None or not token:
        return
    durable_store.fail(claim.session_id, claim.submission_id, token, error)


def _submission_wait_seconds() -> float:
    raw = os.environ.get("OMNIX_RPG_SUBMISSION_WAIT_SECONDS", "120")
    try:
        return max(0.1, min(600.0, float(raw)))
    except (TypeError, ValueError):
        return 120.0


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
