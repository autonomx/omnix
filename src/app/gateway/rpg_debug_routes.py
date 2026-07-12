from __future__ import annotations

from functools import wraps
from time import perf_counter
from typing import Any, Callable

from fastapi import FastAPI, Request

from app.rpg.debug_logging import (
    configure_rpg_debug_logging,
    log_rpg_event,
    new_rpg_trace_id,
    rpg_debug_log_status,
)

_HOOK_SENTINEL = "_omnix_rpg_debug_route_hook_installed"
_MIDDLEWARE_SENTINEL = "_omnix_rpg_debug_middleware_installed"
_ROUTE_SENTINEL = "_omnix_rpg_debug_routes_installed"


def install_rpg_debug_route_hook() -> None:
    configure_rpg_debug_logging()
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return

    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_rpg_debug_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)


def register_rpg_debug_routes(app: FastAPI) -> None:
    configure_rpg_debug_logging()
    _install_rpg_debug_middleware(app)
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.get("/api/rpg/debug/log-status", tags=["rpg-debug"], include_in_schema=False)
    async def rpg_debug_status() -> dict[str, Any]:
        return {"ok": True, **rpg_debug_log_status()}

    @app.post("/api/rpg/debug/event", tags=["rpg-debug"], include_in_schema=False)
    async def rpg_debug_client_event(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {"value": payload}
        event = str(payload.pop("event", "client.event") or "client.event").strip()
        session_id = _optional_text(payload.pop("session_id", None))
        turn_id = _optional_text(payload.pop("turn_id", None))
        trace_id = _optional_text(payload.pop("trace_id", None)) or getattr(request.state, "rpg_trace_id", None)
        duration_ms = payload.pop("duration_ms", None)
        log_rpg_event(
            event if event.startswith("client.") else f"client.{event}",
            category="client",
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            duration_ms=duration_ms if isinstance(duration_ms, (int, float)) else None,
            fields={
                "source": "web",
                "client": request.client.host if request.client else None,
                **payload,
            },
        )
        return {"ok": True, "trace_id": trace_id}


def _install_rpg_debug_middleware(app: FastAPI) -> None:
    if getattr(app.state, _MIDDLEWARE_SENTINEL, False):
        return
    setattr(app.state, _MIDDLEWARE_SENTINEL, True)

    @app.middleware("http")
    async def record_rpg_http_activity(request: Request, call_next: Callable[..., Any]) -> Any:
        path = request.url.path
        if not path.startswith("/api/rpg"):
            return await call_next(request)

        trace_id = request.headers.get("x-omnix-rpg-trace-id") or new_rpg_trace_id("http")
        request.state.rpg_trace_id = trace_id
        started_at = perf_counter()
        request_fields = {
            "method": request.method.upper(),
            "path": path,
            "query": dict(request.query_params),
            "content_type": request.headers.get("content-type"),
            "content_length": request.headers.get("content-length"),
            "client": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }
        log_rpg_event(
            "http.request.started",
            category="http",
            trace_id=trace_id,
            session_id=_session_id_from_path(path),
            fields=request_fields,
        )
        try:
            response = await call_next(request)
        except Exception as exc:
            log_rpg_event(
                "http.request.failed",
                category="http",
                level="error",
                trace_id=trace_id,
                session_id=_session_id_from_path(path),
                duration_ms=(perf_counter() - started_at) * 1000.0,
                fields=request_fields,
                error=exc,
                include_traceback=True,
            )
            raise

        duration_ms = (perf_counter() - started_at) * 1000.0
        response.headers["X-Omnix-Rpg-Trace-Id"] = trace_id
        log_rpg_event(
            "http.request.completed",
            category="http",
            level="error" if response.status_code >= 500 else "warning" if response.status_code >= 400 else "info",
            trace_id=trace_id,
            session_id=_session_id_from_path(path),
            duration_ms=duration_ms,
            fields={
                **request_fields,
                "status_code": response.status_code,
                "response_content_type": response.headers.get("content-type"),
                "response_content_length": response.headers.get("content-length"),
            },
        )
        return response


def _session_id_from_path(path: str) -> str | None:
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 4 and parts[:3] == ["api", "rpg", "sessions"]:
        return parts[3]
    return None


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
