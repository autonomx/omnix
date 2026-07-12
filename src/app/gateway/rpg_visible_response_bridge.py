"""Bind every legacy RPG delivery helper to the canonical presentation contract."""
from __future__ import annotations

from typing import Any

from app.rpg.presentation.visible_response import visible_response_text

_INSTALLED = False


def install_rpg_visible_response_bridge() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from app.gateway import rpg_direct_turn_routes, rpg_session_routes, rpg_turn_job_mirror
    from app.jobs import inline_feature_jobs

    rpg_direct_turn_routes._text = _canonical_text
    rpg_session_routes._foreground_turn_text = _canonical_text
    rpg_turn_job_mirror._visible_turn_text = _canonical_text
    inline_feature_jobs._rpg_turn_visible_text = _canonical_text
    _INSTALLED = True


def _canonical_text(result: dict[str, Any], command: str = "") -> str:
    return visible_response_text(result, command)
