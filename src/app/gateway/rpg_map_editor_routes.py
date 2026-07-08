"""Stateless validation, edit, preview, and export routes for RPG map content."""

from __future__ import annotations

from functools import wraps
import json
from typing import Any, Callable, Mapping, Sequence

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.rpg.map_content_editor import MapContentEditError, apply_map_content_operations
from app.rpg.map_content_validation import validate_map_content

_ROUTE_SENTINEL = "_omnix_rpg_map_editor_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_map_editor_route_hook_installed"


def register_rpg_map_editor_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post("/api/rpg/map-editor/validate", tags=["rpg-map-editor"], include_in_schema=False)
    async def validate_definition(request: Request) -> Response:
        payload = _payload(await request.json())
        report = validate_map_content(payload.get("definition"), **_context(payload.get("context")))
        return JSONResponse({"ok": report.ok, "report": report.as_dict()})

    @app.post("/api/rpg/map-editor/apply", tags=["rpg-map-editor"], include_in_schema=False)
    async def apply_operations(request: Request) -> Response:
        payload = _payload(await request.json())
        try:
            result = apply_map_content_operations(
                payload.get("definition"),
                payload.get("operations", ()),
                **_context(payload.get("context")),
            )
        except MapContentEditError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "ok": False,
                    "error": exc.code,
                    "path": exc.path,
                    "detail": exc.detail,
                },
            ) from exc
        return JSONResponse({"ok": result.report.ok, **result.as_dict()})

    @app.post("/api/rpg/map-editor/export", tags=["rpg-map-editor"], include_in_schema=False)
    async def export_definition(request: Request) -> Response:
        payload = _payload(await request.json())
        report = validate_map_content(payload.get("definition"), **_context(payload.get("context")))
        if not report.ok:
            return JSONResponse({"ok": False, "report": report.as_dict()}, status_code=422)
        name = _safe_filename(_text(payload.get("filename")) or "rpg-map-definition.json")
        body = json.dumps(json.loads(report.canonical_json), ensure_ascii=False, indent=2, sort_keys=True)
        return Response(
            content=f"{body}\n",
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
                "Cache-Control": "no-store",
                "X-Map-Definition-Revision": report.revision,
            },
        )


def _payload(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HTTPException(status_code=422, detail={"ok": False, "error": "request_body_must_be_object"})
    return value


def _context(value: object) -> dict[str, tuple[str, ...]]:
    raw = value if isinstance(value, Mapping) else {}
    return {
        "canonical_route_ids": _strings(raw.get("canonical_route_ids")),
        "known_map_ids": _strings(raw.get("known_map_ids")),
        "allowed_asset_ids": _strings(raw.get("allowed_asset_ids")),
    }


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(sorted({str(item).strip() for item in value if str(item).strip()}))


def _safe_filename(value: str) -> str:
    cleaned = "".join(character for character in value if character.isalnum() or character in {"-", "_", "."})
    if not cleaned.endswith(".json"):
        cleaned = f"{cleaned}.json"
    return cleaned[:120] or "rpg-map-definition.json"


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def install_rpg_map_editor_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_rpg_map_editor_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
