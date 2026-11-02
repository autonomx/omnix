"""A view-dependent action from a view the campaign has moved past (RQ-8.9).

A grid command names the campaign revision the player saw, and a map action the map's definition and overlay
revisions. When the campaign has moved on (another tab, a turn in between), the action is refused with a plain
message and the campaign as it stands now, so the play screen redraws and the player chooses again. A typed turn
needs no such token: it runs on the current state, in arrival order (RQ-1.4).
"""
from __future__ import annotations

from typing import Any, Mapping

STALE_MESSAGES = {
    "stale_tactical_campaign_revision": "The fight moved on since your view of it. Here is how it stands now: "
                                        "choose again.",
    "stale_definition_revision": "The map changed since you looked at it. Here it is as it is now: choose again.",
    "stale_overlay_revision": "The map changed since you looked at it. Here it is as it is now: choose again.",
}


def stale_refusal(session_id: str, detail: Mapping[str, Any]) -> dict[str, Any]:
    """``detail`` as it was, or, for a stale view, with the plain message and the campaign as it stands."""
    error = str(detail.get("error") or "")
    if error not in STALE_MESSAGES:
        return dict(detail)
    from app.apps.rpg.edge.api.payloads.player_view import player_session_view
    from app.apps.rpg.session.service import load_session

    session = load_session(session_id) or {}
    runtime = raw_runtime_state if isinstance(raw_runtime_state := session.get("runtime_state"), dict) else {}
    return {**dict(detail), "stale_view": True, "message": STALE_MESSAGES[error],
            "current_revision": int(runtime.get("state_revision") or 0), "session": player_session_view(session)}


__all__ = ["STALE_MESSAGES", "stale_refusal"]
