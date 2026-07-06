from __future__ import annotations

from fastapi.testclient import TestClient

from app.launcher.control_app import app


def test_launcher_dashboard_preserves_log_scroll_state_during_refresh() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    text = response.text
    assert 'data-log-service-id="${id}"' in text
    assert "function captureLogScrollState()" in text
    assert "function restoreLogScrollState(state)" in text
    assert "const logScrollState = captureLogScrollState();" in text
    assert "restoreLogScrollState(logScrollState);" in text
    assert "pinnedToBottom: maxScrollTop - logEl.scrollTop <= 4" in text
    assert "Math.min(saved.scrollTop, maxScrollTop)" in text
