from __future__ import annotations

import hashlib
import json
from typing import Any


def hermes_rpg_ticket_payload(plan_payload: dict[str, Any]) -> dict[str, Any]:
    plan = raw_plan if isinstance(raw_plan := plan_payload.get("plan"), dict) else plan_payload
    proposal = raw_proposal if isinstance(raw_proposal := plan.get("proposal"), dict) else {}
    validation = raw_validation if isinstance(raw_validation := plan_payload.get("validation"), dict) else {}
    command = str(proposal.get("command") or "").strip()
    return {
        "ok": bool(command),
        "source": "hermes_rpg_ticket",
        "ticket_id": _ticket_id(plan_payload),
        "command": command,
        "valid": validation.get("valid") is True if validation else plan_payload.get("ok") is True,
        "needs_user_step": True,
        "ready": False,
        "state_changed": False,
    }


def _ticket_id(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]
