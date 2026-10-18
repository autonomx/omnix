from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.composition.gateway.main import create_gateway_app
import pytest

# Uses the PostgreSQL-backed runtime; runs in the test-postgres job.
pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def fresh_profile_defaults():
    """The workspace's profile defaults are shared state; start and end without them."""
    from app.persistence.module_repositories import PostgresModuleRecordRepository
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    def clear() -> None:
        with unit_of_work() as work:
            PostgresModuleRecordRepository(work.connection).delete(
                current_tenant(), module="live-chat", record_type="conversation-profiles", record_id="default",
            )
            work.commit()

    clear()
    yield
    clear()


def _create_session(client: TestClient) -> str:
    response = client.post(
        "/api/chat/sessions",
        json={"title": "Live Chat profile"},
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_live_conversation_profile_api_persists_defaults_and_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    monkeypatch.setenv("OMNIX_LIVE_CONVERSATION_PROFILE_PATH", str(tmp_path / "profiles.json"))
    client = TestClient(create_gateway_app(), base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
    session_id = _create_session(client)

    defaults = client.get("/api/live-chat/profile/defaults")
    assert defaults.status_code == 200
    assert defaults.json()["presence_preset"] == "natural"

    updated_defaults = client.patch(
        "/api/live-chat/profile/defaults",
        json={"presence_preset": "engaged", "talkativeness": 70},
    )
    assert updated_defaults.status_code == 200
    assert updated_defaults.json()["profile_version"] == 2

    inherited = client.get(
        f"/api/chat/sessions/{session_id}/live-conversation/profile"
    )
    assert inherited.status_code == 200
    assert inherited.json()["source"] == "user_defaults"
    assert inherited.json()["effective"]["talkativeness"] == 70

    overridden = client.patch(
        f"/api/chat/sessions/{session_id}/live-conversation/profile",
        json={"conversation_stance": "listen", "response_length": "brief"},
    )
    assert overridden.status_code == 200
    assert overridden.json()["source"] == "session_override"
    assert overridden.json()["effective"]["conversation_stance"] == "listen"
    assert overridden.json()["effective"]["presence_preset"] == "engaged"

    cleared = client.delete(
        f"/api/chat/sessions/{session_id}/live-conversation/profile"
    )
    assert cleared.status_code == 200
    assert cleared.json()["source"] == "user_defaults"
    assert cleared.json()["session_override"] is None


def test_live_conversation_profile_api_rejects_missing_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    monkeypatch.setenv("OMNIX_LIVE_CONVERSATION_PROFILE_PATH", str(tmp_path / "profiles.json"))
    client = TestClient(create_gateway_app(), base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})

    response = client.get(
        "/api/chat/sessions/chat:missing/live-conversation/profile"
    )

    assert response.status_code == 404
