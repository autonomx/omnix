"""Version 10's retirement of narrations still pending from before WP-5.6: such a save kept the narration request in
its own queue (``runtime_state.narration_jobs_by_turn``), and every load used to queue it again. The turn's outcome
stands in its interaction; its late narration is no longer written, so the queue goes and the lifecycle says so."""
from __future__ import annotations

from typing import Any

from app.apps.rpg.foundation.state import access as _sections


def retire_pending_narration(document: dict[str, Any]) -> dict[str, Any]:
    runtime = _sections.runtime_state_of(document)
    if not isinstance(runtime, dict):
        return document
    runtime.pop("narration_jobs_by_turn", None)
    lifecycles = runtime.get("interaction_lifecycles")
    for lifecycle in lifecycles.values() if isinstance(lifecycles, dict) else ():
        if isinstance(lifecycle, dict) and lifecycle.get("status") == "narration_pending":
            lifecycle.update(status="narration_retired", narration_status="retired")
    return document


__all__ = ["retire_pending_narration"]
