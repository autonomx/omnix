from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rpg_direct_turn_routes import register_direct_turn_route


def test_direct_turn_route_applies_runtime_without_job_queue(monkeypatch) -> None:
    from app.rpg.session import interactive_first_call_runtime
    from app.rpg.session import service

    calls: list[dict[str, object]] = []

    def apply_turn(session_id: str, command: str, performance_override: dict[str, object] | None = None) -> dict[str, object]:
        calls.append({
            'session_id': session_id,
            'command': command,
            'performance_override': performance_override,
        })
        return {
            'ok': True,
            'final_narration': 'Bran nods from behind the bar.',
            'session': {'state': {'session_id': session_id, 'turn_count': 1}},
        }

    monkeypatch.setattr(interactive_first_call_runtime, 'apply_turn', apply_turn)
    monkeypatch.setattr(service, 'save_session', lambda session, compact=False: {'state': session['state'], 'saved': True})

    app = FastAPI(title='test')
    register_direct_turn_route(app)

    response = TestClient(app).post('/api/rpg/sessions/rpg_test/turn', json={'command': 'i ask bran how he is doing'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['ok'] is True
    assert payload['session_id'] == 'rpg_test'
    assert payload['command'] == 'i ask bran how he is doing'
    assert payload['response'] == 'Bran nods from behind the bar.'
    assert payload['content'] == 'Bran nods from behind the bar.'
    assert payload['session']['saved'] is True
    assert calls == [
        {
            'session_id': 'rpg_test',
            'command': 'i ask bran how he is doing',
            'performance_override': {'enable_live_narration_llm': False},
        }
    ]


def test_direct_turn_route_rejects_missing_command() -> None:
    app = FastAPI(title='test')
    register_direct_turn_route(app)

    response = TestClient(app).post('/api/rpg/sessions/rpg_test/turn', json={})

    assert response.status_code == 400
    assert response.json()['detail']['error'] == 'missing_command'
