from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.audiobook import routes as audiobook_routes
from app.gateway.main import create_gateway_app


def test_audiobook_api_is_registered_on_gateway() -> None:
    gateway = create_gateway_app()
    paths = {route.path for route in gateway.routes}
    assert "/api/audiobook/projects" in paths
    assert "/api/audiobook/source-library" in paths
    assert "/api/audiobook/projects/{project_id}" in paths
    assert any("DELETE" in (route.methods or set()) for route in gateway.routes if route.path == "/api/audiobook/projects/{project_id}")
    assert "/api/audiobook/projects/{project_id}/source" in paths
    assert "/api/audiobook/projects/{project_id}/source/library" in paths
    assert "/api/audiobook/projects/{project_id}/source/download" in paths
    assert "/api/audiobook/projects/{project_id}/cover" in paths
    assert "/api/audiobook/projects/{project_id}/speakers" in paths
    assert "/api/audiobook/projects/{project_id}/speakers/{speaker_id}/casting" in paths
    assert "/api/audiobook/projects/{project_id}/review/{issue_id}" in paths
    assert "/api/audiobook/projects/{project_id}/spans/{span_id}/annotation" in paths
    assert "/api/audiobook/projects/{project_id}/render" in paths
    assert "/api/audiobook/projects/{project_id}/jobs/{job_id}/cancel" in paths
    assert "/api/audiobook/projects/{project_id}/jobs/{job_id}/retry" in paths


def test_gateway_registration_does_not_import_audiobook_runtime_dependencies() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from app.gateway.main import create_gateway_app; "
                "create_gateway_app(); "
                "assert 'app.audiobook.service' not in sys.modules; "
                "assert 'app.providers.faster_qwen3_tts_provider' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).resolve().parents[3],
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_source_library_lists_supported_files_without_leaving_its_root(tmp_path, monkeypatch) -> None:
    (tmp_path / "book.pdf").write_bytes(b"pdf")
    (tmp_path / "notes.txt").write_text("notes", encoding="utf-8")
    (tmp_path / "ignore.exe").write_bytes(b"no")
    monkeypatch.setattr(audiobook_routes, "_source_library_root", lambda: tmp_path)

    payload = audiobook_routes._source_library_files()

    assert [item["name"] for item in payload["files"]] == ["book.pdf", "notes.txt"]
    with pytest.raises(ValueError):
        audiobook_routes._resolve_source_library_file("../outside.txt")


def test_page_exclusion_query_becomes_canonical_extraction_settings() -> None:
    assert audiobook_routes._page_extraction_settings("pdf", "3, 1-2, 2-4") == {
        "excluded_page_ranges": [[1, 4]],
    }
    with pytest.raises(ValueError, match="only supported for PDF"):
        audiobook_routes._page_extraction_settings("txt", "1-3")


def test_source_download_accepts_unicode_filename(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.epub"
    source.write_bytes(b"source bytes")
    service = SimpleNamespace(open_source=lambda _context, project_id: (
        source.open("rb"), "application/epub+zip", "caf\u00e9.epub",
    ))
    monkeypatch.setattr(audiobook_routes, "_service_and_context", lambda: (service, None))
    gateway = FastAPI()
    audiobook_routes.register_audiobook_routes(gateway)

    response = TestClient(gateway).get("/api/audiobook/projects/book-one/source/download")

    assert response.status_code == 200
    assert response.content == b"source bytes"
    assert "filename*=UTF-8''caf%C3%A9.epub" in response.headers["content-disposition"]
