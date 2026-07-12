"""Trace durable RPG session load/save stages inside an active request pipeline."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from app.rpg.performance_trace import current_rpg_pipeline_trace, rpg_pipeline_span

_SENTINEL = "_omnix_session_performance_hook_installed"


def install_session_performance_hook() -> None:
    from app.rpg.session import durable_store, service

    if getattr(service, _SENTINEL, False):
        return

    durable_load = _wrap_if_active(
        service.load_session_from_disk,
        "session.file_read_decode_migrate",
        _load_fields,
    )
    durable_save = _wrap_if_active(
        service.save_session_to_disk,
        "session.serialize_write",
        _save_fields,
    )
    service.load_session_from_disk = durable_load
    service.save_session_to_disk = durable_save
    durable_store.load_session_from_disk = durable_load
    durable_store.save_session_to_disk = durable_save

    service.load_session = _wrap_if_active(
        service.load_session,
        "session.load_total",
        _load_fields,
    )
    service.save_session = _wrap_if_active(
        service.save_session,
        "session.save_total",
        _save_fields,
    )
    service.list_session_summaries = _wrap_if_active(
        service.list_session_summaries,
        "session.list_summaries_total",
        _list_fields,
    )
    setattr(service, _SENTINEL, True)


def _wrap_if_active(
    function: Callable[..., Any],
    span_name: str,
    field_builder: Callable[[tuple[Any, ...], dict[str, Any]], dict[str, Any]],
) -> Callable[..., Any]:
    @wraps(function)
    def traced(*args: Any, **kwargs: Any) -> Any:
        if current_rpg_pipeline_trace() is None:
            return function(*args, **kwargs)
        fields = field_builder(args, kwargs)
        with rpg_pipeline_span(span_name, fields=fields) as span:
            result = function(*args, **kwargs)
            _attach_result_fields(span, result)
            return result

    return traced


def _load_fields(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    session_id = args[0] if args else kwargs.get("session_id")
    return {"session_id": str(session_id or "")}


def _save_fields(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    session = args[0] if args else kwargs.get("session")
    manifest = session.get("manifest") if isinstance(session, dict) and isinstance(session.get("manifest"), dict) else {}
    return {
        "session_id": str(manifest.get("session_id") or manifest.get("id") or ""),
        "compact": bool(kwargs.get("compact", False)),
    }


def _list_fields(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    return {"operation": "list_session_summaries"}


def _attach_result_fields(span: dict[str, Any], result: Any) -> None:
    if isinstance(result, list):
        span["result_count"] = len(result)
        return
    if not isinstance(result, dict):
        span["result_present"] = result is not None
        return
    manifest = result.get("manifest") if isinstance(result.get("manifest"), dict) else {}
    runtime = result.get("runtime_state") if isinstance(result.get("runtime_state"), dict) else {}
    span["result_present"] = True
    span["session_id"] = str(manifest.get("session_id") or manifest.get("id") or span.get("session_id") or "")
    span["interaction_seq"] = runtime.get("interaction_seq")
    span["state_revision"] = runtime.get("state_revision")
