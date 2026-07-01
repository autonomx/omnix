from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .hermes_adapter_contract import hermes_adapter_preview_payload
from .hermes_candidate import hermes_demo_candidate
from .hermes_diagnostics import (
    HermesDiagnosticsTestRequest,
    hermes_diagnostics_status_payload,
    hermes_diagnostics_test_payload,
)
from .hermes_rpg_context import hermes_rpg_context_payload
from .hermes_rpg_plan import hermes_rpg_plan_payload
from .hermes_rpg_suggestions import hermes_rpg_suggestions_payload
from .hermes_rpg_turn_readout import hermes_rpg_turn_readout_payload
from .omnix_mode_policy import omnix_mode_policy_payload
from .omnix_route_decision import omnix_route_decision_payload

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


class HermesAdapterPreviewRequest(BaseModel):
    mode: str = ""
    intent: str = "preview"
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HermesRpgContextRequest(BaseModel):
    session_id: str = ""
    include_recent_turns: bool = True


class HermesRpgSuggestionsRequest(BaseModel):
    session_id: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


class HermesRpgTurnReadoutRequest(BaseModel):
    session_id: str = ""
    turn: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class HermesRpgPlanRequest(BaseModel):
    session_id: str = ""
    turn_id: int | str | None = None
    context_hash: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    enabled: bool | None = None


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


@router.post("/adapter/preview", include_in_schema=False)
def hermes_adapter_preview(request: HermesAdapterPreviewRequest) -> dict[str, Any]:
    return hermes_adapter_preview_payload(request.model_dump())


@router.get("/capabilities", include_in_schema=False)
def hermes_capabilities(mode: str | None = None) -> dict[str, Any]:
    return omnix_mode_policy_payload(mode)


@router.get("/route-decision", include_in_schema=False)
def hermes_route_decision(mode: str | None = None) -> dict[str, Any]:
    return omnix_route_decision_payload(mode)


@router.get("/candidate/demo", include_in_schema=False)
def hermes_candidate_demo(note: str = "ready") -> dict[str, Any]:
    return hermes_demo_candidate(note=note)


@router.post("/rpg/context", include_in_schema=False)
def hermes_rpg_context(request: HermesRpgContextRequest) -> dict[str, Any]:
    return hermes_rpg_context_payload(request.model_dump())


@router.post("/rpg/suggestions", include_in_schema=False)
def hermes_rpg_suggestions(request: HermesRpgSuggestionsRequest) -> dict[str, Any]:
    return hermes_rpg_suggestions_payload(request.model_dump())


@router.post("/rpg/turn-readout", include_in_schema=False)
def hermes_rpg_turn_readout(request: HermesRpgTurnReadoutRequest) -> dict[str, Any]:
    return hermes_rpg_turn_readout_payload(request.model_dump())


@router.post("/plan", include_in_schema=False)
def hermes_rpg_plan(request: HermesRpgPlanRequest) -> dict[str, Any]:
    return hermes_rpg_plan_payload(request.model_dump())


@router.post("/approve", include_in_schema=False)
def hermes_approve(request: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "approvals_disabled",
        "approved": False,
        "mode": "blocked",
        "request": request or {},
    }


@router.post("/lookup", include_in_schema=False)
def hermes_lookup(request: HermesLookupRequest) -> dict[str, Any]:
    from .hermes_readouts import readout_payload

    payload = readout_payload(request.name, request.args)
    return {**payload, "dry_run": True, "mode": "lookup"}
