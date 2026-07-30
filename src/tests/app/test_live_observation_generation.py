from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_live_observation_generation_uses_server_owned_material(monkeypatch) -> None:
    from app import shared
    from app.gateway.live_material_context import live_material_store
    from app.gateway.main import create_gateway_app

    session_id = "observation-contract-test"
    live_material_store.clear(session_id)
    calls: list[dict[str, object]] = []

    def chat_completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(content="Use 'fewer' for countable items.")

    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda provider_name=None: SimpleNamespace(chat_completion=chat_completion),
    )
    client = TestClient(create_gateway_app(), raise_server_exceptions=False)
    appended = client.post(
        f"/api/chat/sessions/{session_id}/live/material",
        json={
            "segment_id": "segment-0",
            "sequence": 0,
            "text": "We have less errors in this draft.",
            "response_policy": "observe",
            "retention": "ephemeral_session",
            "task_contract_id": "editing",
            "task_contract_version": 2,
        },
    )
    assert appended.status_code == 200
    context_version = appended.json()["context_version"]

    response = client.post(
        f"/api/chat/sessions/{session_id}/live/observations/generate",
        json={
            "observation_id": "observation-1",
            "output_id": "output-1",
            "context_version": context_version,
            "task_contract_id": "editing",
            "task_contract_version": 2,
            "task_instruction": "Correct important grammar mistakes while I read.",
            "priority": "normal",
            "anchor_ids": ["segment-0:hash"],
            "preferred_maximum_speech_ms": 2500,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "observation_id": "observation-1",
        "output_id": "output-1",
        "context_version": context_version,
        "task_contract_id": "editing",
        "task_contract_version": 2,
        "text": "Use 'fewer' for countable items.",
        "text_chars": 32,
        "estimated_speech_ms": 1650,
    }
    assert len(calls) == 1
    messages = calls[0]["messages"]
    assert "untrusted data" in messages[0].content
    assert "Recent exact material" in messages[1].content
    assert "less errors" in messages[1].content
    live_material_store.clear(session_id)


def test_live_observation_generation_rejects_stale_context(monkeypatch) -> None:
    from app import shared
    from app.gateway.live_material_context import live_material_store
    from app.gateway.main import create_gateway_app

    session_id = "observation-stale-test"
    live_material_store.clear(session_id)
    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda provider_name=None: SimpleNamespace(
            chat_completion=lambda **kwargs: SimpleNamespace(content="Should not run")
        ),
    )
    client = TestClient(create_gateway_app(), raise_server_exceptions=False)
    appended = client.post(
        f"/api/chat/sessions/{session_id}/live/material",
        json={
            "segment_id": "segment-0",
            "sequence": 0,
            "text": "Material.",
            "response_policy": "observe",
            "task_contract_id": "translation",
            "task_contract_version": 1,
        },
    )
    assert appended.status_code == 200

    response = client.post(
        f"/api/chat/sessions/{session_id}/live/observations/generate",
        json={
            "observation_id": "observation-1",
            "output_id": "output-1",
            "context_version": appended.json()["context_version"] + 1,
            "task_contract_id": "translation",
            "task_contract_version": 1,
            "task_instruction": "Translate into English.",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "live_context_version_changed"
    live_material_store.clear(session_id)
