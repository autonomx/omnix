"""AWS Signature Version 4 against the published S3 examples.

Vectors: AWS S3 API reference, "Signature calculations for the Authorization
header: transferring payload in a single chunk" and "Query string
authentication" (credentials AKIAIOSFODNN7EXAMPLE, 2013-05-24T00:00:00Z).
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import pytest

from app.persistence.blob_store import InvalidBlobKey, normalize_blob_key
from app.persistence.s3_blob_store import S3Settings, SigV4Signer

NOW = datetime(2013, 5, 24, tzinfo=timezone.utc)
EMPTY = hashlib.sha256(b"").hexdigest()


def _signer() -> SigV4Signer:
    return SigV4Signer(
        S3Settings(
            endpoint="https://examplebucket.s3.amazonaws.com",
            bucket="examplebucket",
            access_key_id="AKIAIOSFODNN7EXAMPLE",
            secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
    )


def _signature(headers: dict[str, str]) -> str:
    return headers["authorization"].rsplit("Signature=", 1)[1]


def test_get_object_with_range_matches_the_aws_example() -> None:
    headers = _signer().sign_headers(
        "GET", "/test.txt", headers={"Range": "bytes=0-9"}, payload_sha256=EMPTY, now=NOW
    )
    assert headers["authorization"].startswith(
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
    )
    assert _signature(headers) == "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"


def test_put_object_matches_the_aws_example() -> None:
    body = b"Welcome to Amazon S3."
    headers = _signer().sign_headers(
        "PUT",
        "/test$file.text",
        headers={"Date": "Fri, 24 May 2013 00:00:00 GMT", "x-amz-storage-class": "REDUCED_REDUNDANCY"},
        payload_sha256=hashlib.sha256(body).hexdigest(),
        now=NOW,
    )
    assert _signature(headers) == "98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd"


def test_presigned_get_matches_the_aws_example() -> None:
    url = _signer().presign("GET", "/test.txt", expires_seconds=86400, now=NOW)
    assert url.startswith("https://examplebucket.s3.amazonaws.com/test.txt?X-Amz-Algorithm=AWS4-HMAC-SHA256")
    assert url.endswith("X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404")


@pytest.mark.parametrize("endpoint", ["ftp://minio:9000", "http://minio:9000/path", "minio:9000"])
def test_endpoint_must_be_an_http_origin(endpoint: str) -> None:
    with pytest.raises(ValueError):
        S3Settings(endpoint=endpoint, bucket="b", access_key_id="a", secret_access_key="s")


@pytest.mark.parametrize("key", ["", "/abs", "a/../b", "a//b", "./a"])
def test_unsafe_blob_keys_are_rejected_for_every_backend(key: str) -> None:
    with pytest.raises(InvalidBlobKey):
        normalize_blob_key(key)
