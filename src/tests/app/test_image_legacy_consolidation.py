from __future__ import annotations

import json
from pathlib import Path

from app.assets import SharedAssetStore
from app.image import asset_store as legacy_asset_store
from app.image.job_queue import (
    claim_next_image_job,
    complete_image_job,
    enqueue_image_job,
    list_image_jobs,
    release_image_job,
)
from app.jobs import default_job_store


def test_legacy_image_queue_uses_shared_jobs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMNIX_JOBS_DB_PATH", str(tmp_path / "jobs.sqlite"))
    monkeypatch.setenv("OMNIX_INLINE_IMAGE_JOB_EXECUTOR", "0")

    queued = enqueue_image_job({"prompt": "A moonlit harbor", "width": 768, "height": 768})

    shared = default_job_store().get_job(queued["job_id"])
    assert shared is not None
    assert shared.module == "image-generation"
    assert shared.type == "image.generate"
    assert shared.compat["legacy_queue_bypassed"] is True
    assert [job["job_id"] for job in list_image_jobs()] == [shared.id]

    claimed = claim_next_image_job()
    assert claimed is not None
    assert claimed["job_id"] == shared.id
    assert claimed["lease_token"]

    released = release_image_job(shared.id, claimed["lease_token"])
    assert released is not None
    assert released["status"] == "queued"

    claimed_again = claim_next_image_job()
    assert claimed_again is not None
    completed = complete_image_job(
        shared.id,
        claimed_again["lease_token"],
        {
            "asset_id": "image:shared-result",
            "title": "A moonlit harbor",
            "mime_type": "image/png",
            "width": 768,
            "height": 768,
            "image_bytes": b"not-persisted",
            "local_path": "C:/private/output.png",
        },
    )

    assert completed is not None
    assert completed["status"] == "complete"
    assert completed["result"]["asset_id"] == "image:shared-result"
    assert "image_bytes" not in completed["result"]
    assert "local_path" not in completed["result"]


def test_shared_assets_read_through_legacy_image_manifest(monkeypatch, tmp_path: Path) -> None:
    image_dir = tmp_path / "legacy-images"
    image_dir.mkdir()
    image_path = image_dir / "legacy.png"
    image_path.write_bytes(b"png")
    legacy_manifest = image_dir / "manifest.json"
    legacy_manifest.write_text(
        json.dumps(
            {
                "assets": {
                    "legacy-one": {
                        "path": str(image_path),
                        "mime_type": "image/png",
                        "hash": "abc123",
                        "metadata": {"title": "Legacy one"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(legacy_asset_store, "ASSET_DIR", str(image_dir))
    monkeypatch.setattr(legacy_asset_store, "MANIFEST_PATH", str(legacy_manifest))

    shared_manifest = tmp_path / "shared" / "manifest.json"
    store = SharedAssetStore(manifest_path=shared_manifest)
    assets = {asset.id: asset for asset in store.list_assets().assets}

    assert assets["image:legacy-one"].storage_path == str(image_path)
    assert assets["image:legacy-one"].compat["legacy_asset_id"] == "legacy-one"
    assert not shared_manifest.exists()

    migration = store.import_image_manifest()
    assert migration.would_import == 1
    assert shared_manifest.is_file()
    assert {asset.id for asset in store.list_assets().assets} >= {"image:legacy-one"}
