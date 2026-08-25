"""Gateway routes for the local Codex authentication flow."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def test_codex_auth_status_route_reports_chatgpt_login(monkeypatch) -> None:
    from app.gateway import main

    monkeypatch.setattr(main, "_configured_codex_path", lambda: "codex-test")
    monkeypatch.setattr(
        main.ChatGPTCodexProvider,
        "auth_status",
        classmethod(
            lambda _cls, path: {
                "installed": True,
                "authenticated": True,
                "auth_mode": "chatgpt",
                "cli_version": "codex-test 1.0",
                "detail": "Logged in using ChatGPT",
            }
        ),
    )

    response = TestClient(main.create_gateway_app()).get("/api/providers/chatgpt-codex/auth")

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert response.json()["auth_mode"] == "chatgpt"


def test_codex_login_route_starts_codex_owned_browser_flow(monkeypatch) -> None:
    from app.gateway import main

    monkeypatch.setattr(main, "_configured_codex_path", lambda: "codex-test")
    monkeypatch.setattr(
        main.ChatGPTCodexProvider,
        "start_login",
        classmethod(
            lambda _cls, path: {
                "started": True,
                "pid": 1234,
                "installed": True,
                "authenticated": False,
                "auth_mode": None,
                "cli_version": "codex-test 1.0",
                "detail": "Browser login started",
            }
        ),
    )

    response = TestClient(main.create_gateway_app()).post("/api/providers/chatgpt-codex/login", json={})

    assert response.status_code == 200
    assert response.json()["started"] is True
    assert response.json()["pid"] == 1234
