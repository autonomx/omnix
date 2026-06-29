from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .hermes_diagnostics import (
    HermesDiagnosticsTestRequest,
    hermes_diagnostics_status_payload,
    hermes_diagnostics_test_payload,
)

router = APIRouter(prefix="/api/hermes", tags=["hermes"])


class HermesTestRequest(BaseModel):
    content: str = "house status"
    session_id: str = "diagnostics"
    domain: str = "chat"
    dry_run: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class HermesLookupRequest(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


@router.get("/status", include_in_schema=False)
def hermes_status() -> dict[str, Any]:
    return hermes_diagnostics_status_payload()


@router.post("/test", include_in_schema=False)
def hermes_test(request: HermesTestRequest | None = None) -> dict[str, Any]:
    payload = request or HermesTestRequest()
    return hermes_diagnostics_test_payload(
        HermesDiagnosticsTestRequest(
            content=payload.content,
            session_id=payload.session_id,
            domain=payload.domain,
            metadata={**payload.metadata, "api_dry_run_only": True},
        )
    )


@router.get("/recent", include_in_schema=False)
def hermes_recent() -> dict[str, Any]:
    return {"ok": True, "items": [], "count": 0, "source": "not_configured"}


@router.post("/lookup", include_in_schema=False)
def hermes_lookup(request: HermesLookupRequest) -> dict[str, Any]:
    from .hermes_readouts import readout_payload

    payload = readout_payload(request.name, request.args)
    return {**payload, "dry_run": True, "mode": "lookup"}
