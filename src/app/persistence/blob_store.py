from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from app.runtime_paths import resources_data_root


class InvalidBlobKey(ValueError):
    pass


class BlobIntegrityError(RuntimeError):
    pass


def default_blob_root() -> Path:
    override = (os.environ.get("OMNIX_BLOB_ROOT") or "").strip()
    return Path(override) if override else resources_data_root() / "blobs"


class LocalBlobStore:
    """Atomic filesystem BlobStore for local and offline Omnix deployments."""

    provider = "local-filesystem"

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = (Path(root) if root is not None else default_blob_root()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, storage_key: str, content: bytes) -> dict[str, Any]:
        if not isinstance(content, bytes):
            raise TypeError("BlobStore content must be bytes")
        path = self._path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        checksum = hashlib.sha256(content).hexdigest()
        if path.is_file():
            existing = path.read_bytes()
            if hashlib.sha256(existing).hexdigest() == checksum:
                return self._record(storage_key, path, checksum, len(content), created=False)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=str(path.parent),
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = handle.name
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        return self._record(storage_key, path, checksum, len(content), created=True)

    def read_bytes(self, storage_key: str, *, expected_checksum: str | None = None) -> bytes:
        path = self._path(storage_key)
        content = path.read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        if expected_checksum is not None and actual != expected_checksum:
            raise BlobIntegrityError(
                f"blob checksum mismatch for {storage_key}: expected {expected_checksum}, got {actual}"
            )
        return content

    def delete(self, storage_key: str) -> bool:
        path = self._path(storage_key)
        if not path.exists():
            return False
        path.unlink()
        self._remove_empty_parents(path.parent)
        return True

    def exists(self, storage_key: str) -> bool:
        return self._path(storage_key).is_file()

    def _path(self, storage_key: str) -> Path:
        normalized = str(storage_key).strip().replace("\\", "/")
        if not normalized or normalized.startswith("/"):
            raise InvalidBlobKey("storage key must be a non-empty relative path")
        pieces = normalized.split("/")
        if any(piece in {"", ".", ".."} for piece in pieces):
            raise InvalidBlobKey("storage key contains an unsafe path segment")
        candidate = self.root.joinpath(*pieces).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise InvalidBlobKey("storage key escapes BlobStore root") from exc
        return candidate

    def _remove_empty_parents(self, directory: Path) -> None:
        while directory != self.root:
            try:
                directory.rmdir()
            except OSError:
                return
            directory = directory.parent

    def _record(
        self,
        storage_key: str,
        path: Path,
        checksum: str,
        byte_size: int,
        *,
        created: bool,
    ) -> dict[str, Any]:
        return {
            "storage_provider": self.provider,
            "storage_key": str(storage_key).replace("\\", "/"),
            "byte_size": int(byte_size),
            "checksum_sha256": checksum,
            "path": str(path),
            "created": created,
        }
