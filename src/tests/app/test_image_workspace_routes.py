from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assets import AssetRecord, AssetType, SharedAssetStore as CompatibleSharedAssetStore
from app.assets.store import SharedAssetStore
import app.gateway.image_workspace_routes as image_workspace_routes
import app.image.asset_store as legacy_image_store
from app.jobs import CreateJobRequest, ResourceClass, SQLiteJobStore


def test_image_workspace_routes_are_filtered_and_bounded(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    jobs = SQLiteJobStore(tmp_path / "jobs.sqlite")
    jobs.create_job(
        CreateJobRequest(
            module="image-generation",
            type="image.generate",
            resource_class=ResourceClass.GPU_IMAGE,
            input_payload={"prompt": "one"},
        )
    )
    jobs.create_job(
        CreateJobRequest(
            module="voice",
            type="tts.synthesize",
            resource_class=ResourceClass.GPU_TTS,
            input_payload={"text": "not an image"},
        )
    )

    valid_image = tmp_path / "one.png"
    valid_image.write_bytes(b"png")
    empty_image = tmp_path / "empty.png"
    empty_image.write_bytes(b"")

    assets = SharedAssetStore(tmp_path / "assets.json")
    assets.upsert_asset(
        AssetRecord(
            id="image:one",
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(valid_image),
            created_at="2026-01-02T00:00:00+00:00",
        )
    )
    assets.upsert_asset(
        AssetRecord(
            id="image:missing",
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(tmp_path / "missing.png"),
            created_at="2026-01-03T00:00:00+00:00",
        )
    )
    assets.upsert_asset(
        AssetRecord(
            id="image:empty",
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(empty_image),
            created_at="2026-01-04T00:00:00+00:00",
        )
    )
    assets.upsert_asset(
        AssetRecord(
            id="audio:one",
            module="voice",
            type=AssetType.AUDIO,
            mime_type="audio/wav",
            storage_path=str(tmp_path / "one.wav"),
            created_at="2026-01-05T00:00:00+00:00",
        )
    )

    monkeypatch.setattr(image_workspace_routes, "default_job_store", lambda: jobs)
    monkeypatch.setattr(image_workspace_routes, "default_asset_store", lambda: assets)
    app = FastAPI()
    image_workspace_routes.register_image_workspace_routes(app)
    client = TestClient(app)

    job_response = client.get("/api/image-generation/jobs?limit=1")
    asset_response = client.get("/api/image-generation/assets?limit=10")

    assert job_response.status_code == 200
    assert [job["type"] for job in job_response.json()["jobs"]] == ["image.generate"]
    assert asset_response.status_code == 200
    assert [asset["id"] for asset in asset_response.json()["assets"]] == ["image:one"]


def test_image_workspace_deletes_manifest_asset_and_file(tmp_path, monkeypatch) -> None:
    image_file = tmp_path / "generated.png"
    image_file.write_bytes(b"png")
    assets = SharedAssetStore(tmp_path / "assets.json")
    assets.upsert_asset(
        AssetRecord(
            id="image:generated",
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(image_file),
            created_at="2026-01-02T00:00:00+00:00",
        )
    )

    monkeypatch.setattr(image_workspace_routes, "default_asset_store", lambda: assets)
    app = FastAPI()
    image_workspace_routes.register_image_workspace_routes(app)
    client = TestClient(app)

    response = client.post("/api/image-generation/assets/image%3Agenerated/delete", json={})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "asset_id": "image:generated",
        "deleted": True,
        "file_deleted": True,
    }
    assert image_file.exists() is False
    assert assets.list_assets().assets == []


def test_image_workspace_deletes_legacy_image_manifest_asset(tmp_path, monkeypatch) -> None:
    legacy_dir = tmp_path / "legacy-images"
    legacy_dir.mkdir()
    legacy_file = legacy_dir / "legacy.png"
    legacy_file.write_bytes(b"png")
    legacy_manifest = legacy_dir / "manifest.json"
    legacy_manifest.write_text(
        json.dumps(
            {
                "assets": {
                    "legacy-one": {
                        "path": str(legacy_file),
                        "mime_type": "image/png",
                        "hash": "",
                        "metadata": {"title": "Legacy image"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(legacy_image_store, "ASSET_DIR", str(legacy_dir))
    monkeypatch.setattr(legacy_image_store, "MANIFEST_PATH", str(legacy_manifest))

    assets = CompatibleSharedAssetStore(tmp_path / "shared-assets.json")
    monkeypatch.setattr(image_workspace_routes, "default_asset_store", lambda: assets)
    app = FastAPI()
    image_workspace_routes.register_image_workspace_routes(app)
    client = TestClient(app)

    response = client.delete("/api/image-generation/assets/image%3Alegacy-one")

    assert response.status_code == 200
    assert response.json()["asset_id"] == "image:legacy-one"
    assert response.json()["file_deleted"] is True
    assert legacy_file.exists() is False
    assert json.loads(legacy_manifest.read_text(encoding="utf-8"))["assets"] == {}


def test_image_workspace_jobs_tolerates_store_read_failure(monkeypatch) -> None:
    class BrokenStore:
        def list_jobs(self) -> list[object]:
            raise OSError("transient disk read failure")

    monkeypatch.setattr(image_workspace_routes, "default_job_store", BrokenStore)
    app = FastAPI()
    image_workspace_routes.register_image_workspace_routes(app)
    client = TestClient(app)

    response = client.get("/api/image-generation/jobs")

    assert response.status_code == 200
    assert response.json()["jobs"] == []
