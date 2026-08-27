"""Routing diagnostics/API for Omnix execution lanes."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .router import OmnixRouteDecision, route_omnix_request

router = APIRouter(prefix="/api/assistant-routing", tags=["assistant-routing"])


class RouteRequest(BaseModel):
    content: str


@router.post("/decide", response_model=OmnixRouteDecision)
def decide_route(request: RouteRequest) -> OmnixRouteDecision:
    # Workflow lookup is supplied by the WorkflowRuntime phase; routing remains
    # deterministic and usable when no workflow catalog is configured.
    return route_omnix_request(request.content)
