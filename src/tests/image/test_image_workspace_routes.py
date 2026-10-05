from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assets import AssetRecord, AssetType
from app.assets.store import SharedAssetStore
from app.platform.image.routes.workspace import create_image_workspace_router
import app.platform.image.asset_store as legacy_image_store
from app.jobs import CompleteJobRequest, CreateJobRequest, ResourceClass
from tests.support.in_memory_jobs import InMemoryJobStore


def test_image_workspace_routes_are_filtered_and_bounded(tmp_path, monkeypatch) -> None:
    jobs = InMemoryJobStore(tmp_path / "jobs.sqlite")
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
            id="image:character-avatar",
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(valid_image),
            metadata={"source_module": "character-avatar"},
            created_at="2026-01-04T01:00:00+00:00",
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

    app = FastAPI()
    app.include_router(create_image_workspace_router(jobs, assets))
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
    jobs = InMemoryJobStore(tmp_path / "jobs.sqlite")
    job = jobs.create_job(
        CreateJobRequest(
            module="image-generation",
            type="image.generate",
            resource_class=ResourceClass.GPU_IMAGE,
            input_payload={"prompt": "generated"},
        )
    )
    jobs.complete_job(
        job.id,
        CompleteJobRequest(output_refs=[{"type": "image", "asset_id": "image:generated"}]),
    )
    assets.upsert_asset(
        AssetRecord(
            id="image:generated",
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(image_file),
            source_job_id=job.id,
            created_at="2026-01-02T00:00:00+00:00",
        )
    )

    app = FastAPI()
    app.include_router(create_image_workspace_router(jobs, assets))
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
    assert "image:generated" not in {asset.id for asset in assets.list_assets().assets}
    assert jobs.get_job(job.id) is None


def test_image_workspace_jobs_prunes_deleted_image_result_jobs(tmp_path, monkeypatch) -> None:
    jobs = InMemoryJobStore(tmp_path / "jobs.sqlite")
    job = jobs.create_job(
        CreateJobRequest(
            module="image-generation",
            type="image.generate",
            resource_class=ResourceClass.GPU_IMAGE,
            input_payload={"prompt": "deleted result"},
        )
    )
    jobs.complete_job(
        job.id,
        CompleteJobRequest(output_refs=[{"type": "image", "asset_id": "image:deleted"}]),
    )
    assets = SharedAssetStore(tmp_path / "assets.json")

    app = FastAPI()
    app.include_router(create_image_workspace_router(jobs, assets))
    client = TestClient(app)

    response = client.get("/api/image-generation/jobs")

    assert response.status_code == 200
    assert response.json()["jobs"] == []
    assert jobs.get_job(job.id) is None


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

    def delete_legacy_image_asset(asset_id: str, *, delete_file: bool = True):
        payload = json.loads(legacy_manifest.read_text(encoding="utf-8"))
        legacy = payload["assets"].pop(asset_id, None)
        legacy_manifest.write_text(json.dumps(payload), encoding="utf-8")
        file_deleted = False
        if legacy and delete_file:
            legacy_file.unlink(missing_ok=True)
            file_deleted = True
        return {"deleted": legacy is not None, "file_deleted": file_deleted}

    monkeypatch.setattr(legacy_image_store, "delete_image_asset", delete_legacy_image_asset)

    assets = SharedAssetStore(tmp_path / "shared-assets.json")
    assets.upsert_asset(
        AssetRecord(
            id="image:legacy-one",
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(legacy_file),
            created_at="2026-01-02T00:00:00+00:00",
            compat={"legacy_asset_id": "legacy-one"},
        )
    )
    jobs = InMemoryJobStore(tmp_path / "jobs.sqlite")
    app = FastAPI()
    app.include_router(create_image_workspace_router(jobs, assets))
    client = TestClient(app)

    response = client.delete("/api/image-generation/assets/image%3Alegacy-one")

    assert response.status_code == 200
    assert response.json()["asset_id"] == "image:legacy-one"
    assert response.json()["file_deleted"] is True
    assert legacy_file.exists() is False
    assert json.loads(legacy_manifest.read_text(encoding="utf-8"))["assets"] == {}


def test_image_workspace_jobs_tolerates_store_read_failure(tmp_path) -> None:
    class BrokenStore:
        def list_jobs(self) -> list[object]:
            raise OSError("transient disk read failure")

    jobs = BrokenStore()
    assets = SharedAssetStore(tmp_path / "assets.json")
    app = FastAPI()
    app.include_router(create_image_workspace_router(jobs, assets))
    client = TestClient(app)

    response = client.get("/api/image-generation/jobs")

    assert response.status_code == 200
    assert response.json()["jobs"] == []
