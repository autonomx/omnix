from __future__ import annotations

from .core import AssistantResult, ToolResult
from .house_mock import apply_house_mock
from .mode_review import hold_for_review, review_call


def apply_mode_result(result: AssistantResult, *, dry_run: bool) -> AssistantResult:
    if result.domain != "house" or not result.tool_calls:
        return result
    rows: list[ToolResult] = []
    for call in result.tool_calls:
        decision = review_call(call)
        if decision.requires_confirmation and not dry_run:
            return hold_for_review(result, call, dry_run=dry_run)
        try:
            rows.append(apply_house_mock(call, dry_run=dry_run))
        except Exception as exc:
            rows.append(ToolResult(name=call.name, ok=False, error=str(exc), executed=False))
    result.tool_results = rows
    result.success = all(item.ok for item in rows)
    if result.success and rows and dry_run:
        result.response = f"Dry run: {result.response}"
    elif result.success and rows:
        result.response = describe_result(rows[-1], fallback=result.response)
    return result


def describe_result(row: ToolResult, *, fallback: str) -> str:
    if row.name == "set_light":
        room = str(row.output.get("room", "room")).replace("_", " ")
        state = str(row.output.get("state", "updated"))
        return f"{room.title()} lights are {state}."
    if row.name == "set_brightness":
        room = str(row.output.get("room", "room")).replace("_", " ")
        brightness = row.output.get("brightness", "updated")
        return f"{room.title()} brightness is set to {brightness}%."
    return fallback
