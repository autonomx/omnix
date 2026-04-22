"""Global queue runner (IMG-4)."""
from __future__ import annotations

from app.image.job_queue import claim_next_image_job, complete_image_job
from app.image.service import generate_image
from app.image.asset_store import (
    save_image_asset_bytes,
    register_image_asset_file,
)


def run_one_image_job():
    job = claim_next_image_job()
    if not job:
        return {"ok": True, "message": "no_jobs"}

    payload = job["payload"]
    result = generate_image(payload)

    if not result.ok:
        complete_image_job(job["job_id"], job["lease_token"], {"error": result.error})
        return {"ok": False}

    asset_id = payload.get("request_id") or job["job_id"]

    if result.local_path:
        path = register_image_asset_file(result.local_path, asset_id, result.metadata)
    else:
        path = save_image_asset_bytes(
            result.metadata.get("image_bytes", b""),
            result.mime_type,
            asset_id,
            result.metadata,
        )

    complete_image_job(
        job["job_id"],
        job["lease_token"],
        {
            "asset_id": asset_id,
            "path": path,
        },
    )

    return {"ok": True, "job_id": job["job_id"]}
