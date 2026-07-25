"""Atomic local spool for generated World Forge candidates awaiting PostgreSQL."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _root() -> Path:
    configured = str(os.environ.get("OMNIX_RPG_WORLD_GENERATION_SPOOL_DIR") or "").strip()
    return Path(configured or "resources/data/world-generation-spool")


def _safe_job_id(job_id: str) -> str:
    safe = _SAFE.sub("-", str(job_id)).strip("-")[:140]
    digest = hashlib.sha256(str(job_id).encode("utf-8")).hexdigest()[:16]
    return f"{safe or 'job'}-{digest}.json"


def spool_path(job_id: str) -> Path:
    return _root() / _safe_job_id(job_id)


def write_candidate_spool(job_id: str, payload: Mapping[str, Any]) -> Path:
    """Write one complete candidate artifact atomically and durably."""

    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    target = spool_path(job_id)
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=root,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        try:
            directory_fd = os.open(root, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def read_candidate_spool(job_id: str) -> dict[str, Any] | None:
    target = spool_path(job_id)
    if not target.exists():
        return None
    value = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"world_generation_spool_invalid:{job_id}")
    return dict(value)


def delete_candidate_spool(job_id: str) -> None:
    spool_path(job_id).unlink(missing_ok=True)


__all__ = [
    "delete_candidate_spool",
    "read_candidate_spool",
    "spool_path",
    "write_candidate_spool",
]
