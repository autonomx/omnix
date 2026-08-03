from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.launcher import huggingface_token_control as token_control
from app.launcher import runtime_control_app
from app.launcher.huggingface_token_store import (
    huggingface_token_path,
    load_huggingface_token,
)

_TEST_TOKEN = "hf_" + "a" * 32


class _FakeManager:
    def __init__(self) -> None:
        self.restarted: list[str] = []
        self.stopped: list[str] = []

    def restart(self, service_id: str):
        self.restarted.append(service_id)
        return {"ok": True, "service_id": service_id}

    def stop(self, service_id: str):
        self.stopped.append(service_id)
        return {"ok": True, "service_id": service_id}


def _configure_local_store(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMNIX_LAUNCHER_SECRET_DIR", str(tmp_path / "secrets"))
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)


def test_runtime_launcher_html_exposes_masked_huggingface_token_control() -> None:
    client = TestClient(runtime_control_app.app)

    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert 'id="hf-token-panel"' in text
    assert 'id="hf-token-input"' in text
    assert 'type="password"' in text
    assert "Save token &amp; start download" in text
    assert "Clear token" in text
    assert "/api/launcher/hugging-face-token" in text
    assert "HUGGING_FACE_HUB_TOKEN" not in text


def test_saving_token_persists_locally_and_restarts_moshi(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_local_store(monkeypatch, tmp_path)
    manager = _FakeManager()
    monkeypatch.setattr(token_control, "get_default_manager", lambda: manager)
    monkeypatch.setattr(token_control, "_model_cache_path", lambda: tmp_path / "missing")
    client = TestClient(runtime_control_app.app)

    response = client.put(
        "/api/launcher/hugging-face-token",
        json={"token": _TEST_TOKEN},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["source"] == "local_file"
    assert payload["model_cached"] is False
    assert manager.restarted == ["kyutai_moshi"]
    assert _TEST_TOKEN not in response.text
    assert load_huggingface_token(Path("F:/unused")) == _TEST_TOKEN
    assert huggingface_token_path(Path("F:/unused")).is_file()

    status_response = client.get("/api/launcher/hugging-face-token")
    assert status_response.status_code == 200
    assert status_response.json() == {
        "configured": True,
        "source": "local_file",
        "model_cached": False,
    }
    assert _TEST_TOKEN not in status_response.text


def test_invalid_placeholder_token_is_rejected_without_restarting(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_local_store(monkeypatch, tmp_path)
    manager = _FakeManager()
    monkeypatch.setattr(token_control, "get_default_manager", lambda: manager)
    client = TestClient(runtime_control_app.app)

    response = client.put(
        "/api/launcher/hugging-face-token",
        json={"token": "hf_YOUR_TOKEN"},
    )

    assert response.status_code == 422
    assert manager.restarted == []
    assert not huggingface_token_path(Path("F:/unused")).exists()


def test_clearing_token_removes_local_secret_and_stops_moshi(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_local_store(monkeypatch, tmp_path)
    manager = _FakeManager()
    monkeypatch.setattr(token_control, "get_default_manager", lambda: manager)
    client = TestClient(runtime_control_app.app)

    saved = client.put(
        "/api/launcher/hugging-face-token",
        json={"token": _TEST_TOKEN},
    )
    assert saved.status_code == 200

    response = client.delete("/api/launcher/hugging-face-token")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert manager.stopped == ["kyutai_moshi"]
    assert load_huggingface_token(Path("F:/unused")) is None
    assert not huggingface_token_path(Path("F:/unused")).exists()
