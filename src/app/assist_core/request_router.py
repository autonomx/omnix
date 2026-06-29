from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .core import ToolCall, ToolResult, ToolRiskLevel
from .house_mock import apply_house_mock


@dataclass
class RoutedRequest:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False


@dataclass
class RoutedResult:
    ok: bool
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    dry_run: bool = False


ALLOWED_NAMES = {
    "get_house_status",
    "set_light",
    "set_brightness",
    "suggest_podcast_plan",
    "suggest_rpg_director_beat",
}


def route_request(request: RoutedRequest) -> RoutedResult:
    if request.name not in ALLOWED_NAMES:
        return RoutedResult(ok=False, name=request.name, error="not_allowed", dry_run=request.dry_run)

    if request.name in {"get_house_status", "set_light", "set_brightness"}:
        try:
            result: ToolResult = apply_house_mock(
                ToolCall(name=request.name, args=request.args, risk=ToolRiskLevel.LOW),
                dry_run=request.dry_run,
            )
            return RoutedResult(ok=result.ok, name=request.name, payload=result.output, error=result.error, dry_run=request.dry_run)
        except Exception as exc:
            return RoutedResult(ok=False, name=request.name, error=str(exc), dry_run=request.dry_run)

    return RoutedResult(ok=True, name=request.name, payload={"accepted": True, "payload": request.args}, dry_run=request.dry_run)
