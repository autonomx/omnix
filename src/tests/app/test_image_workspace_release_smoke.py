from __future__ import annotations

from fastapi.testclient import TestClient

from app.assets import SharedAssetStore
from app.gateway.main import create_gateway_app
import app.gateway.image_asset_routes as image_asset_routes
import app.gateway.image_workspace_routes as image_workspace_routes
from app.image.models import ImageGenerationResponse
from app.jobs import SQLiteJobStore
from app.jobs.image_inline import execute_image_job


def test_image_workspace_release_flow_survives_reload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")
    jobs = SQLiteJobStore(tmp_path / "jobs.sqlite")
    assets = SharedAssetStore(tmp_path / "assets" / "manifest.json")
    image_path = tmp_path / "generated" / "harbor.png"
    image_path.parent.mkdir()
    image_path.write_bytes(b"PNG-release-smoke")

    monkeypatch.setattr(image_workspace_routes, "default_job_store", lambda: jobs)
    monkeypatch.setattr(image_workspace_routes, "default_asset_store", lambda: assets)
    monkeypatch.setattr(image_asset_routes, "default_asset_store", lambda: assets)

    client = TestClient(
        create_gateway_app(
            job_store_factory=lambda: jobs,
            asset_store_factory=lambda: assets,
        )
    )
    queued_response = client.post(
        "/api/jobs",
        json={
            "module": "image-generation",
            "type": "image.generate",
            "resource_class": "gpu:image",
            "input_payload": {
                "prompt": "A moonlit harbor",
                "provider_id": "image:mock",
                "width": 1024,
                "height": 768,
            },
        },
    )

    assert queued_response.status_code == 200
    queued = queued_response.json()
    assert queued["status"] == "queued"
    job = jobs.get_job(queued["id"])
    assert job is not None

    completed = execute_image_job(
        jobs,
        job,
        asset_store=assets,
        generate_fn=lambda payload: ImageGenerationResponse(
            ok=True,
            provider=payload["provider"],
            status="completed",
            local_path=str(image_path),
            width=payload["width"],
            height=payload["height"],
            mime_type="image/png",
        ),
    )

    assert completed.status.value == "completed"
    assert len(completed.output_refs) == 1
    output_ref = completed.output_refs[0]
    asset_id = output_ref["asset_id"]
    assert "storage_path" not in output_ref
    assert "local_path" not in output_ref

    job_projection = client.get("/api/image-generation/jobs").json()["jobs"]
    asset_projection = client.get("/api/image-generation/assets").json()["assets"]
    assert job_projection[0]["id"] == completed.id
    assert job_projection[0]["output_refs"][0]["asset_id"] == asset_id
    assert asset_projection[0]["id"] == asset_id
    assert asset_projection[0]["source_job_id"] == completed.id

    inline = client.get(f"/api/assets/{asset_id}/file")
    download = client.get(f"/api/assets/{asset_id}/file?download=true")
    assert inline.status_code == 200
    assert inline.content == b"PNG-release-smoke"
    assert inline.headers["content-disposition"].startswith("inline")
    assert download.status_code == 200
    assert download.headers["content-disposition"].startswith("attachment")

    event_stream = client.get("/api/jobs/events?after_id=0&limit=20").text
    assert "event: job.created" in event_stream
    assert "event: job.completed" in event_stream

    reloaded_client = TestClient(
        create_gateway_app(
            job_store_factory=lambda: SQLiteJobStore(tmp_path / "jobs.sqlite"),
            asset_store_factory=lambda: SharedAssetStore(tmp_path / "assets" / "manifest.json"),
        )
    )
    reloaded_assets = reloaded_client.get("/api/image-generation/assets").json()["assets"]
    assert [asset["id"] for asset in reloaded_assets] == [asset_id]
    assert reloaded_client.get(f"/api/assets/{asset_id}/file").content == b"PNG-release-smoke"
