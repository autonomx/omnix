from __future__ import annotations

from datetime import datetime
from functools import wraps
from typing import Any, Callable

from app.rpg.debug_logging import configure_rpg_debug_logging, log_rpg_event

_SENTINEL = "_omnix_rpg_debug_job_hook_installed"


def install_rpg_debug_job_hook(sqlite_job_store_cls: Any) -> None:
    """Record the durable lifecycle of every RPG job without changing job semantics."""

    if getattr(sqlite_job_store_cls, _SENTINEL, False):
        return

    configure_rpg_debug_logging()
    _wrap_create_job(sqlite_job_store_cls)
    _wrap_job_method(sqlite_job_store_cls, "mark_running", "job.running")
    _wrap_job_method(sqlite_job_store_cls, "update_progress", "job.progress")
    _wrap_job_method(sqlite_job_store_cls, "complete_job", "job.completed")
    _wrap_job_method(sqlite_job_store_cls, "fail_job", "job.failed", error_level=True)
    _wrap_job_method(sqlite_job_store_cls, "cancel_job", "job.cancelled", error_level=True)
    setattr(sqlite_job_store_cls, _SENTINEL, True)


def _wrap_create_job(sqlite_job_store_cls: Any) -> None:
    original: Callable[..., Any] = sqlite_job_store_cls.create_job

    @wraps(original)
    def create_job_with_debug(self: Any, request: Any) -> Any:
        try:
            job = original(self, request)
        except Exception as exc:
            if _is_rpg_request(request):
                log_rpg_event(
                    "job.create_failed",
                    category="job",
                    level="error",
                    session_id=_request_session_id(request),
                    fields={"request": _request_fields(request), "db_path": str(getattr(self, "db_path", ""))},
                    error=exc,
                    include_traceback=True,
                )
            raise
        if _is_rpg_job(job):
            log_rpg_event(
                "job.created_or_reused",
                category="job",
                session_id=_job_session_id(job),
                fields={"job": _job_fields(job), "db_path": str(getattr(self, "db_path", ""))},
            )
        return job

    sqlite_job_store_cls.create_job = create_job_with_debug


def _wrap_job_method(
    sqlite_job_store_cls: Any,
    method_name: str,
    event_name: str,
    *,
    error_level: bool = False,
) -> None:
    original: Callable[..., Any] = getattr(sqlite_job_store_cls, method_name)

    @wraps(original)
    def method_with_debug(self: Any, job_id: str, *args: Any, **kwargs: Any) -> Any:
        try:
            job = original(self, job_id, *args, **kwargs)
        except Exception as exc:
            existing = _safe_get_job(self, job_id)
            if _is_rpg_job(existing):
                log_rpg_event(
                    f"{event_name}.exception",
                    category="job",
                    level="error",
                    session_id=_job_session_id(existing),
                    fields={
                        "job_id": job_id,
                        "method": method_name,
                        "args": args,
                        "kwargs": kwargs,
                        "db_path": str(getattr(self, "db_path", "")),
                    },
                    error=exc,
                    include_traceback=True,
                )
            raise
        if _is_rpg_job(job):
            log_rpg_event(
                event_name,
                category="performance" if event_name in {"job.completed", "job.failed"} else "job",
                level="error" if error_level and event_name == "job.failed" else "info",
                session_id=_job_session_id(job),
                duration_ms=_job_duration_ms(job),
                fields={
                    "job": _job_fields(job),
                    "method": method_name,
                    "db_path": str(getattr(self, "db_path", "")),
                },
                error=_job_error_message(job) if event_name == "job.failed" else None,
            )
        return job

    setattr(sqlite_job_store_cls, method_name, method_with_debug)


def _is_rpg_request(request: Any) -> bool:
    return str(getattr(request, "module", "") or "") == "rpg" or str(getattr(request, "type", "") or "").startswith("rpg.")


def _is_rpg_job(job: Any) -> bool:
    return job is not None and (
        str(getattr(job, "module", "") or "") == "rpg"
        or str(getattr(job, "type", "") or "").startswith("rpg.")
    )


def _request_session_id(request: Any) -> str | None:
    input_ref = getattr(request, "input_ref", None)
    if isinstance(input_ref, dict):
        value = str(input_ref.get("session_id") or "").strip()
        return value or None
    return None


def _job_session_id(job: Any) -> str | None:
    input_ref = getattr(job, "input_ref", None)
    if isinstance(input_ref, dict):
        value = str(input_ref.get("session_id") or "").strip()
        return value or None
    return None


def _request_fields(request: Any) -> dict[str, Any]:
    model_dump = getattr(request, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump(mode="json")
        except Exception:
            pass
    return {
        "module": getattr(request, "module", None),
        "type": getattr(request, "type", None),
        "input_ref": getattr(request, "input_ref", None),
        "input_payload": getattr(request, "input_payload", None),
    }


def _job_fields(job: Any) -> dict[str, Any]:
    stages = getattr(job, "stages", None)
    progress = getattr(job, "progress", None)
    error = getattr(job, "error", None)
    return {
        "id": getattr(job, "id", None),
        "module": getattr(job, "module", None),
        "type": getattr(job, "type", None),
        "status": _enum_value(getattr(job, "status", None)),
        "resource_class": _enum_value(getattr(job, "resource_class", None)),
        "priority": getattr(job, "priority", None),
        "input_ref": getattr(job, "input_ref", None),
        "input_payload": getattr(job, "input_payload", None),
        "output_refs": getattr(job, "output_refs", None),
        "progress": _model_value(progress),
        "stages": [_model_value(stage) for stage in stages] if isinstance(stages, list) else [],
        "error": _model_value(error),
        "created_at": getattr(job, "created_at", None),
        "started_at": getattr(job, "started_at", None),
        "completed_at": getattr(job, "completed_at", None),
        "updated_at": getattr(job, "updated_at", None),
    }


def _safe_get_job(store: Any, job_id: str) -> Any:
    try:
        return store.get_job(job_id)
    except Exception:
        return None


def _job_duration_ms(job: Any) -> float | None:
    started = _parse_datetime(getattr(job, "started_at", None)) or _parse_datetime(getattr(job, "created_at", None))
    completed = _parse_datetime(getattr(job, "completed_at", None)) or _parse_datetime(getattr(job, "updated_at", None))
    if started is None or completed is None:
        return None
    return max(0.0, (completed - started).total_seconds() * 1000.0)


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _job_error_message(job: Any) -> str | None:
    error = getattr(job, "error", None)
    if error is None:
        return None
    message = getattr(error, "message", None)
    return str(message or error)


def _model_value(value: Any) -> Any:
    if value is None:
        return None
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump(mode="json")
        except Exception:
            return str(value)
    return value


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)
