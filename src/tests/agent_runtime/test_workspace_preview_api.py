from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from app.agent_runtime import preview_api
from app.agent_runtime.contracts import AgentRunSnapshot, AgentRunSpec, ModelRef, WorkspaceSpec


class _Service:
    def __init__(self, snapshot: AgentRunSnapshot | None) -> None:
        self.snapshot = snapshot

    def get(self, run_id: str) -> AgentRunSnapshot | None:
        if self.snapshot is None or self.snapshot.run_id != run_id:
            return None
        return self.snapshot


def _snapshot(root: Path) -> AgentRunSnapshot:
    spec = AgentRunSpec(
        run_id="run-preview",
        task="Create an HTML page",
        objective="Create an HTML page",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="test"),
        workspace=WorkspaceSpec(
            root=str(root),
            worktree=str(root),
            allowed_paths=["**"],
            forbidden_paths=["private/**"],
        ),
    )
    return AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="completed")


def test_preview_serves_html_with_browser_sandbox_headers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "index.html").write_text("<h1>Hello</h1><script>document.body.dataset.ready='1'</script>", encoding="utf-8")
    monkeypatch.setattr(preview_api, "_service", lambda: _Service(_snapshot(tmp_path)))

    response = preview_api.get_agent_workspace_preview("run-preview", "index.html")

    assert isinstance(response, FileResponse)
    assert response.media_type == "text/html"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    csp = response.headers["content-security-policy"]
    assert "connect-src 'none'" in csp
    assert "sandbox allow-scripts" in csp
    assert "form-action 'none'" in csp


def test_preview_source_is_plain_text_and_utf8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    markup = "<!doctype html><title>Preview</title>"
    (tmp_path / "index.html").write_text(markup, encoding="utf-8")
    monkeypatch.setattr(preview_api, "_service", lambda: _Service(_snapshot(tmp_path)))

    response = preview_api.get_agent_workspace_preview("run-preview", "index.html", source=True)

    assert isinstance(response, PlainTextResponse)
    assert response.body.decode("utf-8") == markup
    assert response.headers["cache-control"] == "no-store"


def test_preview_rejects_workspace_escape_forbidden_and_non_web_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "index.html").write_text("<p>ok</p>", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a browser artifact", encoding="utf-8")
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "secret.html").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(preview_api, "_service", lambda: _Service(_snapshot(tmp_path)))

    with pytest.raises(HTTPException) as escape:
        preview_api.get_agent_workspace_preview("run-preview", "../index.html")
    assert escape.value.status_code == 403

    with pytest.raises(HTTPException) as forbidden:
        preview_api.get_agent_workspace_preview("run-preview", "private/secret.html")
    assert forbidden.value.status_code == 403

    with pytest.raises(HTTPException) as unsupported:
        preview_api.get_agent_workspace_preview("run-preview", "notes.txt")
    assert unsupported.value.status_code == 415
