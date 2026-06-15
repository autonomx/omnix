"""Contract tests proving the classic browser UI is retired."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _client() -> TestClient:
    from run_app import app

    return TestClient(app, raise_server_exceptions=False)


def test_run_app_root_is_backend_status_not_classic_html() -> None:
    response = _client().get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["ok"] is True
    assert payload["browser_ui"] == "apps/web"
    assert payload["gateway"] == "app.gateway.main:app"


def test_run_app_no_longer_serves_classic_static_files() -> None:
    response = _client().get("/static/script.js")

    assert response.status_code == 404


def test_run_app_generated_images_remain_data_surface(tmp_path, monkeypatch) -> None:
    import app.runtime_paths as runtime_paths
    import run_app

    image_root = tmp_path / "generated_images"
    image_root.mkdir()
    image = image_root / "scene.png"
    image.write_bytes(b"png")

    monkeypatch.setattr(runtime_paths, "generated_images_root", lambda: image_root)
    monkeypatch.setattr(run_app, "generated_images_root", lambda: image_root)

    response = _client().get("/generated-images/scene.png")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content == b"png"


def test_run_app_missing_generated_image_reports_diagnostic(tmp_path, monkeypatch) -> None:
    import app.runtime_paths as runtime_paths
    import run_app

    image_root = tmp_path / "generated_images"
    image_root.mkdir()

    monkeypatch.setattr(runtime_paths, "generated_images_root", lambda: image_root)
    monkeypatch.setattr(run_app, "generated_images_root", lambda: image_root)

    response = _client().get("/generated-images/missing.png")

    assert response.status_code == 404
    assert response.json() == {"ok": False, "error": "file_not_found"}


def test_run_app_rejects_generated_image_path_traversal(tmp_path, monkeypatch) -> None:
    import app.runtime_paths as runtime_paths
    import run_app

    image_root = tmp_path / "generated_images"
    image_root.mkdir()

    monkeypatch.setattr(runtime_paths, "generated_images_root", lambda: image_root)
    monkeypatch.setattr(run_app, "generated_images_root", lambda: image_root)

    response = _client().get("/generated-images/../secret.png")

    assert response.status_code in {400, 404}
    if response.status_code == 400:
        assert response.json() == {"ok": False, "error": "invalid_filename"}
