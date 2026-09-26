"""Bind audiobook render identities to the installed, local TTS artifacts."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from app.shared import load_settings


_MODEL_SUFFIXES = {".safetensors", ".json", ".txt", ".model"}


class ModelIdentityError(ValueError):
    retryable = False


def _configured_model_dir() -> Path:
    # Keep gateway/Audiobook route registration lightweight. The FasterQwen
    # provider imports NumPy and other synthesis dependencies that unrelated
    # gateway workflows do not install. Resolve the concrete model only when
    # model identity is actually requested.
    from app.providers.faster_qwen3_tts_provider import _resolve_qwen3_model_name
    from app.providers.vendor.qwen3_tts.loader import _resolve_model_source

    settings = load_settings().get("faster-qwen3-tts", {})
    source = _resolve_model_source(_resolve_qwen3_model_name(settings))
    directory = Path(source).expanduser().resolve()
    if not directory.is_dir():
        raise ModelIdentityError("a local, pinned FasterQwen model directory is required")
    if not list(directory.glob("*.safetensors")):
        raise ModelIdentityError("the configured FasterQwen model has no weight files")
    return directory


@lru_cache(maxsize=4)
def _fingerprint(filenames: tuple[tuple[str, int, int], ...], directory: str) -> str:
    digest = hashlib.sha256()
    root = Path(directory)
    for relative, size, modified_ns in filenames:
        path = root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        stat = path.stat()
        if stat.st_size != size or stat.st_mtime_ns != modified_ns:
            raise ModelIdentityError("TTS model changed while its revision was being measured")
    return f"sha256:{digest.hexdigest()}"


def current_model_identity(provider_id: str = "faster-qwen3-tts") -> dict[str, object]:
    if provider_id != "faster-qwen3-tts":
        raise ModelIdentityError(f"verified audiobook model identity is unavailable for {provider_id}")
    directory = _configured_model_dir()
    files = sorted(
        (path for path in directory.rglob("*")
         if path.is_file() and path.suffix.lower() in _MODEL_SUFFIXES),
        key=lambda path: path.relative_to(directory).as_posix(),
    )
    fingerprints = tuple(
        (path.relative_to(directory).as_posix(), path.stat().st_size,
         path.stat().st_mtime_ns) for path in files
    )
    if not fingerprints:
        raise ModelIdentityError("the configured FasterQwen model has no artifacts")
    return {"provider_id": provider_id, "model_id": "Qwen3-TTS",
            "model_revision": _fingerprint(fingerprints, str(directory)),
            "artifact_count": len(fingerprints)}


def assert_model_revision(provider_id: str, model_id: str, expected: str) -> None:
    identity = current_model_identity(provider_id)
    if identity["model_id"] != model_id or identity["model_revision"] != expected:
        raise ModelIdentityError("audiobook model revision does not match installed artifacts")
