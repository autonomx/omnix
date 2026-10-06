"""Image outputs reach gateways on other hosts through the shared blob store (WP-5.8)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from services.image import image_service_runtime
from app.assets import content
from app.platform.image import jobs as image_jobs
from app.persistence import blob_store as blob_module
from app.persistence.blob_store import LocalBlobStore


def test_service_publishes_outputs_only_for_remote_blob_storage(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "service-disk" / "out.png"
    output.parent.mkdir()
    output.write_bytes(b"\x89PNG generated")
    shared = LocalBlobStore(tmp_path / "bucket")
    monkeypatch.setattr(blob_module, "default_blob_store", lambda: shared)

    monkeypatch.setattr(blob_module, "blob_backend", lambda: "local")
    assert image_service_runtime._publish_shared_output(str(output)) == {}

    monkeypatch.setattr(blob_module, "blob_backend", lambda: "s3")
    published = image_service_runtime._publish_shared_output(str(output))
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    assert published == {
        "blob_key": f"image-outputs/{checksum[:2]}/{checksum}.png",
        "checksum_sha256": checksum,
    }
    assert image_service_runtime._publish_shared_output(str(tmp_path / "missing.png")) == {}


def test_gateway_reads_a_shared_output_it_cannot_see_on_disk(tmp_path: Path, monkeypatch) -> None:
    payload = b"\x89PNG generated elsewhere"
    remote = LocalBlobStore(tmp_path / "bucket")
    record = remote.put_bytes("image-outputs/ab/out.png", payload)
    # A store without local paths behaves like S3 for materialization.
    remote_view = SimpleNamespace(
        copy_verified_to=remote.copy_verified_to,
        exists=remote.exists,
    )
    monkeypatch.setattr(content, "default_blob_store", lambda: remote_view)
    monkeypatch.setattr(content, "resources_data_root", lambda: tmp_path / "gateway-data")

    result = SimpleNamespace(
        local_path="/image-service-host/only/out.png",
        blob_key=record["storage_key"],
        checksum_sha256=record["checksum_sha256"],
    )
    path = Path(image_jobs._shared_output_path(result))
    assert path.read_bytes() == payload
    assert str(path).startswith(str(tmp_path / "gateway-data"))

    tampered = SimpleNamespace(blob_key=record["storage_key"], checksum_sha256="0" * 64)
    try:
        image_jobs._shared_output_path(tampered)
    except Exception as exc:  # integrity failure must not yield a path
        assert "checksum" in str(exc)
    else:
        raise AssertionError("tampered shared output was accepted")
    assert image_jobs._shared_output_path(SimpleNamespace(blob_key="", checksum_sha256="")) == ""
