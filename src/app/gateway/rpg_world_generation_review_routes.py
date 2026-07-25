"""Game Master review routes for single-pass World Forge candidates."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Request

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work
from app.rpg.debug_logging import new_rpg_trace_id
from app.rpg.worlds.generation_retry import retry_failed_world_generation

_ROUTE_SENTINEL = "_omnix_rpg_world_generation_review_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_world_generation_review_hook_installed"


def _body(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HTTPException(
            status_code=422,
            detail={"ok": False, "error": "request_body_must_be_object"},
        )
    return value


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(
            status_code=404,
            detail={"ok": False, "error": str(exc).strip("'")},
        )
    if isinstance(exc, ValueError):
        return HTTPException(
            status_code=409,
            detail={"ok": False, "error": str(exc)},
        )
    return HTTPException(
        status_code=500,
        detail={"ok": False, "error": "world_generation_review_internal_error"},
    )


def _run_with_results(run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    context = bootstrap_local_tenant(None)
    with unit_of_work(None) as work:
        run = work.world_generation.get(context, run_id)
        if run is None:
            work.rollback()
            raise KeyError(f"world_generation_run_not_found:{run_id}")
        results = work.world_generation.list_topic_results(context, run_id=run_id)
        parent_run_id = str(run.get("parent_run_id") or "")
        parent_results = (
            work.world_generation.list_topic_results(context, run_id=parent_run_id)
            if parent_run_id
            else []
        )
        work.rollback()
    parent_by_topic = {
        str(row.get("topic_id") or ""): row for row in parent_results
    }
    augmented = [
        {
            **row,
            "previous_result": parent_by_topic.get(str(row.get("topic_id") or "")),
        }
        for row in results
    ]
    return run, augmented


def _results(run_id: str) -> list[dict[str, Any]]:
    return _run_with_results(run_id)[1]


def register_rpg_world_generation_review_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.get(
        "/api/rpg/world-generation/{run_id}/results",
        include_in_schema=False,
    )
    def rpg_world_generation_results(run_id: str) -> dict[str, Any]:
        try:
            run, results = _run_with_results(run_id)
            return {
                "ok": True,
                "run_id": run_id,
                "parent_run_id": run.get("parent_run_id"),
                "topic_results": results,
            }
        except Exception as exc:
            raise _error(exc) from exc

    @app.get(
        "/api/rpg/world-generation/{run_id}/results/{topic_id}",
        include_in_schema=False,
    )
    def rpg_world_generation_topic_result(
        run_id: str,
        topic_id: str,
    ) -> dict[str, Any]:
        try:
            run, results = _run_with_results(run_id)
            result = next(
                (
                    row
                    for row in results
                    if str(row.get("topic_id") or "") == topic_id
                ),
                None,
            )
            if result is None:
                raise KeyError(
                    f"world_generation_topic_result_not_found:{run_id}:{topic_id}"
                )
            return {
                "ok": True,
                "run_id": run_id,
                "parent_run_id": run.get("parent_run_id"),
                "topic_result": result,
            }
        except Exception as exc:
            raise _error(exc) from exc

    @app.post(
        "/api/rpg/world-generation/{run_id}/retry-review",
        include_in_schema=False,
    )
    async def rpg_world_generation_retry_review(
        run_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        topic_ids = tuple(
            str(value)
            for value in payload.get("topic_ids") or ()
            if str(value)
        )
        retry_scopes = payload.get("retry_scopes")
        if retry_scopes is not None and not isinstance(retry_scopes, Mapping):
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "retry_scopes_must_be_object"},
            )
        diagnostic_id = new_rpg_trace_id("world-generation-manual-retry")
        try:
            return retry_failed_world_generation(
                run_id,
                selected_topic_ids=topic_ids,
                retry_scopes=(
                    retry_scopes if isinstance(retry_scopes, Mapping) else {}
                ),
                diagnostic_id=diagnostic_id,
            )
        except Exception as exc:
            raise _error(exc) from exc


def install_rpg_world_generation_review_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (
            args and args[0] == "Omnix Web Gateway"
        ):
            register_rpg_world_generation_review_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)


__all__ = [
    "install_rpg_world_generation_review_hook",
    "register_rpg_world_generation_review_routes",
]
