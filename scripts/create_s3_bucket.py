"""Create the configured S3 bucket (OMNIX_S3_*); an existing bucket is fine.

Compose runs it once before the gateway when blobs live in the `storage`
profile's S3 store; the multihost topology test uses it too.
"""
from __future__ import annotations

import hashlib
import os
import time

import httpx


def create_bucket(timeout_seconds: float = 90) -> None:
    from app.persistence.s3_blob_store import S3Settings, SigV4Signer

    endpoint = os.environ["OMNIX_S3_ENDPOINT"]
    settings = S3Settings(
        endpoint=endpoint,
        bucket=os.environ["OMNIX_S3_BUCKET"],
        access_key_id=os.environ["OMNIX_S3_ACCESS_KEY_ID"],
        secret_access_key=os.environ["OMNIX_S3_SECRET_ACCESS_KEY"],
    )
    path = f"/{settings.bucket}"
    deadline = time.monotonic() + timeout_seconds
    while True:
        # Fresh signature per attempt; the store may still be starting.
        headers = SigV4Signer(settings).sign_headers("PUT", path, payload_sha256=hashlib.sha256(b"").hexdigest())
        try:
            response = httpx.put(f"{endpoint.rstrip('/')}{path}", headers=headers, timeout=30)
            if response.status_code in {200, 409}:
                return
            failure = f"{response.status_code} {response.text[:300]}"
        except httpx.HTTPError as exc:
            failure = repr(exc)
        if time.monotonic() > deadline:
            raise RuntimeError(f"bucket creation failed: {failure}")
        time.sleep(1)


if __name__ == "__main__":
    create_bucket()
    print(f"bucket {os.environ['OMNIX_S3_BUCKET']} ready")
