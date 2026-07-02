from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Body

from .hermes_rpg_approved_config import (
    hermes_rpg_approved_flow_config_payload,
    hermes_rpg_approved_flow_feature_enabled,
)
from .hermes_rpg_approved_flow import hermes_rpg_approved_flow
from .hermes_rpg_canonical_submitter import hermes_rpg_canonical_submitter
from .hermes_rpg_execution_ledger import hermes_rpg_execution_ledger_recent, hermes_rpg_execution_ledger_record
from .hermes_rpg_flow_readout import hermes_rpg_flow_readout
from .hermes_rpg_submit_bridge import RpgSubmitter

hermes_rpg_approved_bp = APIRouter()


def hermes_rpg_approved_flow_enabled(
    payload: dict[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> bool:
    return payload.get("enabled") is True and hermes_rpg_approved_flow_feature_enabled(environ)


def hermes_rpg_approved_flow_route_payload(
    payload: dict[str, Any] | None,
    *,
    submitter: RpgSubmitter | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    config = hermes_rpg_approved_flow_config_payload(environ)
    if not hermes_rpg_approved_flow_enabled(data, environ=environ):
        return {
            "ok": False,
            "source": "hermes_rpg_approved_flow_route",
            "error": "hermes_rpg_approved_flow_disabled",
            "enabled": False,
            "config": config,
            "state_changed": False,
        }

    user_step = data.get("user_step") if isinstance(data.get("user_step"), dict) else {}
    replay_entry = data.get("replay_entry") if isinstance(data.get("replay_entry"), dict) else {}
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    flow = hermes_rpg_approved_flow(
        user_step,
        replay_entry,
        context,
        submitter or hermes_rpg_canonical_submitter,
    )
    readout = hermes_rpg_flow_readout(flow)
    ledger_entry = hermes_rpg_execution_ledger_record(payload=data, config=config, flow=flow, readout=readout)
    return {
        "ok": flow.get("ok") is True,
        "source": "hermes_rpg_approved_flow_route",
        "enabled": True,
        "config": config,
        "flow": flow,
        "readout": readout,
        "ledger_entry": ledger_entry,
        "state_changed": flow.get("state_changed") is True,
    }


@hermes_rpg_approved_bp.post("/api/hermes/rpg/approved-flow")
def hermes_rpg_approved_flow_route(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    return hermes_rpg_approved_flow_route_payload(payload)


@hermes_rpg_approved_bp.get("/api/hermes/rpg/approved-flow/config")
def hermes_rpg_approved_flow_config_route() -> dict[str, object]:
    return hermes_rpg_approved_flow_config_payload()


@hermes_rpg_approved_bp.get("/api/hermes/rpg/approved-flow/ledger")
def hermes_rpg_approved_flow_ledger_route(limit: int = 20) -> dict[str, object]:
    return hermes_rpg_execution_ledger_recent(limit)
