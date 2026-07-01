from __future__ import annotations

from typing import TypedDict


class OmnixModeSurface(TypedDict):
    method: str
    path: str
    read_only: bool
    executes: bool
    requires_review: bool


def omnix_mode_surfaces() -> list[OmnixModeSurface]:
    return [
        {
            "method": "GET",
            "path": "modes_metadata",
            "read_only": True,
            "executes": False,
            "requires_review": False,
        },
        {
            "method": "POST",
            "path": "agent_plan",
            "read_only": True,
            "executes": False,
            "requires_review": True,
        },
        {
            "method": "GET",
            "path": "agent_plan_status",
            "read_only": True,
            "executes": False,
            "requires_review": True,
        },
    ]
