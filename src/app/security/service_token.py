"""Authentication dependency for operator-issued internal service credentials."""
from __future__ import annotations

import hmac
import os
import re

from fastapi import HTTPException, Request


def valid_service_token(supplied: list[str]) -> bool:
    """Accept exactly one credential against the currently issued environment token."""
    expected = os.environ.get("OMNIX_SERVICE_TOKEN", "")
    return bool(
        re.fullmatch(r"[A-Za-z0-9_-]{43,}", expected)
        and len(supplied) == 1
        and hmac.compare_digest(expected.encode("utf-8"), supplied[0].encode("utf-8"))
    )


def service_headers() -> dict[str, str]:
    """Headers for an Omnix sidecar only; callers must disable redirects."""
    token = os.environ.get("OMNIX_SERVICE_TOKEN", "")
    if not valid_service_token([token]):
        raise RuntimeError("service_credential_unavailable")
    return {"X-Omnix-Client": "gateway", "X-Omnix-Service-Token": token}


def require_service_token(request: Request) -> None:
    supplied = request.headers.getlist("x-omnix-service-token")
    # token_urlsafe(32) supplies at least 256 bits and produces 43 characters.
    if not valid_service_token(supplied):
        raise HTTPException(status_code=401, detail="invalid_service_token")
