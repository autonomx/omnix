"""Campaign Genesis readiness checks."""
from __future__ import annotations

from typing import Any, Mapping


class CampaignLaunchBlockedError(RuntimeError):
    pass


class IncompleteDossierError(RuntimeError):
    pass


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def campaign_launch_readiness(session: Mapping[str, Any]) -> dict[str, Any]:
    runtime = _mapping(session.get("runtime_state"))
    gate = _mapping(runtime.get("campaign_launch_gate"))
    setup = _mapping(session.get("setup_payload"))
    state = _mapping(session.get("state"))
    enabled = bool(_mapping(setup.get("world_forge"))) or bool(state.get("campaign_bible"))
    if not enabled:
        return {"enabled": False, "ready": True, "reason": "not_required"}
    ready = gate.get("ready") is True
    return {
        "enabled": True,
        "ready": ready,
        "required_before_first_turn": gate.get("required_before_first_turn", True),
        "missing_requirements": list(gate.get("missing_requirements") or ()),
        "reason": "ready" if ready else "campaign_genesis_incomplete",
    }


def require_campaign_launch_ready(session: Mapping[str, Any]) -> dict[str, Any]:
    result = campaign_launch_readiness(session)
    if not result["ready"]:
        raise CampaignLaunchBlockedError(
            "campaign genesis is incomplete: "
            + ",".join(result.get("missing_requirements") or ())
        )
    return result


def dossier_readiness(session: Mapping[str, Any], entity_id: str) -> dict[str, Any]:
    state = _mapping(session.get("state"))
    entity_id = str(entity_id or "").strip()
    if entity_id.startswith("npc:"):
        dossier = _mapping(_mapping(state.get("npc_dossiers")).get(entity_id))
        kind = "npc"
        required = ("name", "appearance", "personality", "backstory", "goals", "motives", "speech_style")
    elif entity_id.startswith("location:"):
        dossier = _mapping(_mapping(state.get("location_dossiers")).get(entity_id))
        kind = "location"
        required = ("name", "sensory_profile", "region_id")
    else:
        return {"entity_id": entity_id, "kind": "unknown", "ready": True, "reason": "not_required"}
    missing = [field for field in required if not dossier.get(field)]
    ready = dossier.get("dossier_status") == "complete" and not missing
    return {
        "entity_id": entity_id,
        "kind": kind,
        "ready": ready,
        "missing_fields": missing,
        "reason": "ready" if ready else "incomplete_dossier",
    }


def require_dossier_ready(session: Mapping[str, Any], entity_id: str) -> dict[str, Any]:
    result = dossier_readiness(session, entity_id)
    if not result["ready"]:
        raise IncompleteDossierError(
            f"incomplete dossier for {entity_id}: "
            + ",".join(result.get("missing_fields") or ())
        )
    return result
