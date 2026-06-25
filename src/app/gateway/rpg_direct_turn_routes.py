from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request

_ROUTE_SENTINEL = '_omnix_direct_turn_registered'
_HOOK_SENTINEL = '_omnix_direct_turn_hook_installed'


def register_direct_turn_route(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post('/api/rpg/sessions/{session_id}/turn', tags=['rpg-session'])
    async def apply_turn_route(session_id: str, http_request: Request) -> dict[str, Any]:
        payload = await http_request.json()
        command = _command(payload)
        from app.rpg.session import interactive_first_call_runtime
        from app.rpg.session.service import load_session, save_session
        result = interactive_first_call_runtime.apply_turn(
            session_id,
            command,
            performance_override={'enable_live_narration_llm': False},
        )
        if result.get('ok') is not True:
            status_code = 404 if result.get('error') == 'session_not_found' else 400
            raise HTTPException(status_code=status_code, detail=result)
        result_session = result.get('session')
        session = save_session(result_session, compact=False) if isinstance(result_session, dict) else load_session(session_id)
        text = _text(result, command)
        return {
            'ok': True,
            'session_id': session_id,
            'command': command,
            'response': text,
            'content': text,
            'result': result,
            'session': session,
            'game': session.get('state', {}) if isinstance(session, dict) else {},
        }


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
