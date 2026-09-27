"""Launcher-owned service credentials, protected by the local operating system."""
from __future__ import annotations

import os
from pathlib import Path
import re
import secrets
import stat
import sys
import tempfile

from app.persistence import provider_secret_store

_WINDOWS_PREFIX = b"OMNIX_SERVICE_TOKEN_DPAPI_V1\n"


class ServiceCredentialError(RuntimeError):
    pass


def _windows() -> bool:
    return sys.platform == "win32"


def _validate(token: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{43,}", token):
        raise ServiceCredentialError("invalid_service_token_configuration")
    return token


def service_credential_path() -> Path:
    if _windows():
        return provider_secret_store.provider_secret_path().with_name("service-token.dpapi")
    return Path(__file__).resolve().parents[3] / "resources/data/secure/service-token"


def _read(path: Path) -> str:
    if path.is_symlink():
        raise ServiceCredentialError("service_credential_symlink_forbidden")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ServiceCredentialError("service_credential_not_regular")
        if not _windows() and (
            metadata.st_mode & 0o077 or metadata.st_uid != os.getuid()
        ):
            raise ServiceCredentialError("service_credential_permissions_unsafe")
        value = os.read(descriptor, 65537)
        if len(value) > 65536:
            raise ServiceCredentialError("service_credential_too_large")
        if _windows():
            if not value.startswith(_WINDOWS_PREFIX):
                raise ServiceCredentialError("service_credential_format_invalid")
            value = provider_secret_store._unprotect(value[len(_WINDOWS_PREFIX):])
        return _validate(value.decode("ascii"))
    except (UnicodeError, ValueError, OSError) as exc:
        raise ServiceCredentialError("service_credential_unreadable") from exc
    finally:
        os.close(descriptor)


def load_or_create_service_token(path: Path | None = None) -> str:
    """Publish an entire protected credential atomically, without overwriting it."""
    target = path or service_credential_path()
    try:
        return _read(target)
    except FileNotFoundError:
        pass
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    token = secrets.token_urlsafe(32)
    value = token.encode("ascii")
    if _windows():
        value = _WINDOWS_PREFIX + provider_secret_store._protect(value)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".service-token-", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # A concurrent launcher can win; it never observes a partial file.
            os.link(temporary, target)
        except FileExistsError:
            return _read(target)
        return token
    finally:
        temporary.unlink(missing_ok=True)


def initialize_service_token() -> str:
    """Initialize once in a launcher; children inherit this exact credential."""
    configured = os.environ.get("OMNIX_SERVICE_TOKEN")
    if configured is None and os.environ.get("OMNIX_AUTH_MODE", "local") != "local":
        raise ServiceCredentialError("service_token_required_for_nonlocal_mode")
    token = _validate(configured) if configured is not None else load_or_create_service_token()
    os.environ["OMNIX_SERVICE_TOKEN"] = token
    return token
