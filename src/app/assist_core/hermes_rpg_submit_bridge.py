from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .hermes_rpg_pipeline_result import hermes_rpg_pipeline_result

RpgSubmitter = Callable[[dict[str, Any]], dict[str, Any]]


def hermes_rpg_submit_bridge(packet: dict[str, Any], submitter: RpgSubmitter) -> dict[str, Any]:
    if packet.get("ready_for_rpg_pipeline") is not True:
        return {
            "ok": False,
            "source": "hermes_rpg_submit_bridge",
            "error": "packet_not_ready",
            "state_changed": False,
        }
    command = str(packet.get("command_text") or "").strip()
    if not command:
        return {
            "ok": False,
            "source": "hermes_rpg_submit_bridge",
            "error": "missing_command",
            "state_changed": False,
        }
    result = submitter({"session_id": packet.get("session_id"), "command_text": command})
    return hermes_rpg_pipeline_result(packet, result)
