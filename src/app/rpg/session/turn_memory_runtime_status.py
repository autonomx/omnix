from __future__ import annotations

from typing import Any

from app.rpg.session.turn_memory_common import d

HOOK_FORMAT_VERSION = "phase14_33_turn_memory_runtime_hook_v1"


def attach_hook_status(
    result: dict[str, Any],
    *,
    attached: bool,
    persisted: bool = False,
    error: str = "",
) -> dict[str, Any]:
    hook_status: dict[str, Any] = {
        "format_version": HOOK_FORMAT_VERSION,
        "attached": attached,
        "deterministic": True,
        "presentation_only": True,
    }
    if attached:
        hook_status.update({"persisted": persisted, "state_path": "runtime_state.turn_memory"})
    if error:
        hook_status["error"] = error
    result["turn_memory_runtime_hook"] = hook_status
    nested = d(result.get("result"))
    if nested:
        nested["turn_memory_runtime_hook"] = dict(hook_status)
        result["result"] = nested
    return result
