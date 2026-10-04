from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.rpg.hermes.adapter_contract import hermes_adapter_preview_payload
from app.rpg.hermes.context import hermes_rpg_context_payload
from app.rpg.hermes.plan import hermes_rpg_plan_payload
from app.rpg.hermes.suggestions import hermes_rpg_suggestions_payload
from app.rpg.hermes.turn_readout import hermes_rpg_turn_readout_payload
from app.rpg.hermes.mode_routing import omnix_mode_policy_payload
from app.rpg.hermes.mode_routing import omnix_route_decision_payload

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


class HermesDiagnosticsPaths(BaseModel):
    status_path: str
    test_path: str
    test_dry_run_only: bool


class HermesStatusResponse(BaseModel):
    """Sidecar reachability and the runtime configuration that reaches it."""

    enabled: bool
    reachable: bool
    state: str
    message: str
    base_url: str
    health: dict[str, Any]
    capabilities: dict[str, Any]
    error: str | None
    timeout_seconds: float
    api_key_configured: bool
    diagnostics: HermesDiagnosticsPaths


@router.get("/status", response_model=HermesStatusResponse)
def hermes_status() -> dict[str, Any]:
    from app.chat.contracts import hermes_assist_status_payload

    return hermes_assist_status_payload()


@router.post("/test")
def hermes_test(request: HermesTestRequest | None = None) -> dict[str, Any]:
    # Imported on use: diagnostics are not needed to compose the gateway.
    from app.chat.contracts import hermes_assist_test_payload

    payload = request or HermesTestRequest()
    return hermes_assist_test_payload(
        content=payload.content,
        session_id=payload.session_id,
        domain=payload.domain,
        metadata={**payload.metadata, "api_dry_run_only": True},
    )


@router.get("/recent")
def hermes_recent() -> dict[str, Any]:
    return {"ok": True, "items": [], "count": 0, "source": "not_configured"}


@router.post("/adapter/preview")
def hermes_adapter_preview(request: HermesAdapterPreviewRequest) -> dict[str, Any]:
    return hermes_adapter_preview_payload(request.model_dump())


@router.get("/capabilities")
def hermes_capabilities(mode: str | None = None) -> dict[str, Any]:
    return omnix_mode_policy_payload(mode)


@router.get("/route-decision")
def hermes_route_decision(mode: str | None = None) -> dict[str, Any]:
    return omnix_route_decision_payload(mode)


@router.get("/candidate/demo")
def hermes_candidate_demo(note: str = "ready") -> dict[str, Any]:
    from app.rpg.hermes.candidate import hermes_demo_candidate

    return hermes_demo_candidate(note=note)


@router.post("/rpg/context")
def hermes_rpg_context(request: HermesRpgContextRequest) -> dict[str, Any]:
    return hermes_rpg_context_payload(request.model_dump())


@router.post("/rpg/suggestions")
def hermes_rpg_suggestions(request: HermesRpgSuggestionsRequest) -> dict[str, Any]:
    return hermes_rpg_suggestions_payload(request.model_dump())


@router.post("/rpg/turn-readout")
def hermes_rpg_turn_readout(request: HermesRpgTurnReadoutRequest) -> dict[str, Any]:
    return hermes_rpg_turn_readout_payload(request.model_dump())


@router.post("/plan")
def hermes_rpg_plan(request: HermesRpgPlanRequest) -> dict[str, Any]:
    return hermes_rpg_plan_payload(request.model_dump())


@router.post("/approve")
def hermes_approve(request: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "approvals_disabled",
        "approved": False,
        "mode": "blocked",
        "request": request or {},
    }


@router.post("/lookup")
def hermes_lookup(request: HermesLookupRequest) -> dict[str, Any]:
    from app.chat.contracts import hermes_assist_readout_payload

    payload = hermes_assist_readout_payload(request.name, request.args)
    return {**payload, "dry_run": True, "mode": "lookup"}
