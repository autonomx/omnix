from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.platform.assistant_tools import browser_adapter


def test_browser_session_generation_cache_has_capacity_ttl_and_clear(monkeypatch) -> None:
    browser_adapter._BROWSER_SESSION_GENERATIONS.clear()
    monkeypatch.setattr(browser_adapter, "_MAX_BROWSER_SESSION_GENERATIONS", 2)
    monkeypatch.setattr(browser_adapter, "_BROWSER_SESSION_GENERATION_TTL_SECONDS", 5.0)
    now = {"value": 10.0}
    monkeypatch.setattr(browser_adapter.time, "monotonic", lambda: now["value"])

    for session_id in ("one", "two", "three"):
        browser_adapter._rotate_browser_session(
            SimpleNamespace(session_id=session_id, proposal_id=None)
        )

    assert list(browser_adapter._BROWSER_SESSION_GENERATIONS) == ["two", "three"]
    browser_adapter._clear_browser_session_generation(
        SimpleNamespace(session_id="two", proposal_id=None)
    )
    assert "two" not in browser_adapter._BROWSER_SESSION_GENERATIONS

    now["value"] = 16.0
    browser_adapter._session_name("three")
    assert browser_adapter._BROWSER_SESSION_GENERATIONS == {}


def test_playwright_session_registry_is_bounded_and_expiring(monkeypatch) -> None:
    browser_adapter._PLAYWRIGHT_SESSIONS.clear()
    monkeypatch.setattr(browser_adapter, "_MAX_PLAYWRIGHT_SESSIONS", 1)
    existing = browser_adapter._PlaywrightSession(name="existing")
    browser_adapter._PLAYWRIGHT_SESSIONS[existing.name] = existing

    with pytest.raises(RuntimeError, match="browser session capacity"):
        browser_adapter._playwright_session(
            SimpleNamespace(session_id="new", proposal_id=None)
        )

    stopped: list[object] = []
    monkeypatch.setattr(
        browser_adapter,
        "_stop_playwright_session",
        lambda session: stopped.append(session),
    )
    existing.expires_at = 1.0
    browser_adapter._expire_playwright_session("existing", existing, 1.0)
    assert browser_adapter._PLAYWRIGHT_SESSIONS == {}
    assert stopped == [existing]


def test_workspace_preview_expiry_reaps_state_and_process(monkeypatch) -> None:
    browser_adapter._PREVIEWS.clear()
    now = {"value": 20.0}
    monkeypatch.setattr(browser_adapter.time, "monotonic", lambda: now["value"])

    class _Timer:
        cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    process = object()
    timer = _Timer()
    browser_adapter._PREVIEWS["expired"] = browser_adapter._WorkspacePreview(
        process=process,
        url="http://127.0.0.1:9000",
        port=9000,
        timer=timer,
        expires_at=10.0,
    )
    terminated: list[object] = []
    monkeypatch.setattr(
        browser_adapter,
        "_terminate_preview_process",
        lambda candidate: terminated.append(candidate),
    )

    browser_adapter._prune_expired_workspace_previews()

    assert browser_adapter._PREVIEWS == {}
    assert timer.cancelled is True
    assert terminated == [process]
