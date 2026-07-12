from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request

from app.gateway.rpg_turn_pipeline import execute_foreground_rpg_turn

_ROUTE_SENTINEL = '_omnix_direct_turn_registered'
_HOOK_SENTINEL = '_omnix_direct_turn_hook_installed'


def register_direct_turn_route(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post('/api/rpg/sessions/{session_id}/turn', tags=['rpg-session'], include_in_schema=False)
    async def apply_turn_route(session_id: str, http_request: Request) -> Any:
        payload = await http_request.json()
        command = _command(payload)
        return await execute_foreground_rpg_turn(
            session_id=session_id,
            command=command,
            request=http_request,
        )


def install_direct_turn_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get('title') == 'Omnix Web Gateway' or (args and args[0] == 'Omnix Web Gateway'):
            register_direct_turn_route(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)


def _command(payload: Any) -> str:
    if isinstance(payload, dict):
        value = payload.get('command') or payload.get('player_input') or payload.get('text') or payload.get('message')
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise HTTPException(status_code=400, detail={'ok': False, 'error': 'missing_command'})


def _text(result: dict[str, Any], command: str) -> str:
    for key in ('final_narration', 'narration', 'summary', 'response', 'content'):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = result.get('result')
    if isinstance(nested, dict):
        return _text(nested, command)
    authoritative = result.get('authoritative')
    if isinstance(authoritative, dict):
        return _text(authoritative, command)
    return f'Your command is accepted: {command}.'
