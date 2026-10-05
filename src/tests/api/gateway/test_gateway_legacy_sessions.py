"""Legacy session compatibility contract tests for the gateway."""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.revisions: dict[str, int] = {}

    def list(self, *, module: str, record_type: str, limit: int):
        del module, record_type
        return [(key, value, 1) for key, value in list(self.records.items())[:limit]]

    def read(self, *, module: str, record_type: str, record_id: str, default: Any = None):
        del module, record_type
        return self.records.get(record_id, default)

    def read_versioned(self, *, module: str, record_type: str, record_id: str, default: Any = None):
        del module, record_type
        if record_id not in self.records:
            return default, 0
        return dict(self.records[record_id]), self.revisions.get(record_id, 1)

    def write(
        self,
        payload: dict[str, Any],
        *,
        module: str,
        record_type: str,
        record_id: str,
        expected_revision: int | None = None,
    ) -> None:
        del module, record_type
        current = self.revisions.get(record_id, 1) if record_id in self.records else 0
        if expected_revision is not None and expected_revision != current:
            from app.persistence.document_store import DocumentRevisionConflict

            raise DocumentRevisionConflict(record_id)
        self.records[record_id] = dict(payload)
        self.revisions[record_id] = current + 1

    def delete(self, *, module: str, record_type: str, record_id: str) -> bool:
        del module, record_type
        return self.records.pop(record_id, None) is not None


def _client() -> TestClient:
    from app.composition.gateway.main import create_gateway_app

    return TestClient(
        create_gateway_app(),
        base_url="http://localhost",
        raise_server_exceptions=False,
        headers={"X-Omnix-Client": "test"},
    )


def test_gateway_legacy_sessions_crud_contract(monkeypatch) -> None:
    from app.platform.chat import legacy_session_api as legacy_sessions
    documents = InMemoryDocumentStore()
    monkeypatch.setattr(legacy_sessions, "_store", lambda: documents)
    monkeypatch.setattr(legacy_sessions, "get_global_system_prompt", lambda: "System prompt")
    client = _client()

    create_response = client.post("/api/sessions")
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["success"] is True
    session_id = created["session_id"]

    list_response = client.get("/api/sessions")
    assert list_response.status_code == 200
    assert list_response.json()["sessions"][0]["id"] == session_id

    get_response = client.get(f"/api/sessions/{session_id}")
    assert get_response.status_code == 200
    assert get_response.json()["session"]["messages"] == []
    assert get_response.json()["session"]["system_prompt"] == "System prompt"

    update_response = client.put(
        f"/api/sessions/{session_id}",
        json={"title": "Renamed", "system_prompt": "Updated prompt"},
    )
    assert update_response.status_code == 200
    assert update_response.json() == {"success": True}
    assert documents.records[session_id]["title"] == "Renamed"
    assert documents.records[session_id]["system_prompt"] == "Updated prompt"

    delete_response = client.delete(f"/api/sessions/{session_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"success": True}
    assert session_id not in documents.records

    missing_response = client.get(f"/api/sessions/{session_id}")
    assert missing_response.status_code == 404


def test_gateway_legacy_sessions_list_orders_newest_first(monkeypatch) -> None:
    from app.platform.chat import legacy_session_api as legacy_sessions
    documents = InMemoryDocumentStore()
    documents.records = {
        "old": {"title": "Old", "updated_at": "2026-06-14T00:00:00"},
        "new": {"title": "New", "updated_at": "2026-06-15T00:00:00"},
    }
    monkeypatch.setattr(legacy_sessions, "_store", lambda: documents)

    response = _client().get("/api/sessions")

    assert response.status_code == 200
    assert [session["id"] for session in response.json()["sessions"]] == ["new", "old"]


def test_gateway_legacy_generate_title_uses_safe_fallback_without_provider() -> None:
    response = _client().post(
        "/api/sessions/generate-title",
        json={"user_message": "Explain the redesigned web app\nwith details", "ai_response": "Sure"},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "title": "Explain the redesigned web app"}
