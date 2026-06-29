from __future__ import annotations

import re

from .core import AssistantRequest, AssistantResult, ToolCall, ToolRiskLevel

ROOMS = ("kitchen", "living room", "living_room", "bedroom", "office")


def infer_house_plan(request: AssistantRequest) -> AssistantResult:
    text = request.message.strip().lower()
    room = find_room(text)

    if "status" in text:
        calls = [ToolCall(name="get_house_status", risk=ToolRiskLevel.LOW)]
        return AssistantResult(success=True, response="I can check the house status.", domain="house", tool_calls=calls)

    if "brightness" in text or "dim" in text:
        calls = [ToolCall(name="set_brightness", args={"room": room, "brightness": find_brightness(text)}, risk=ToolRiskLevel.LOW)]
        return AssistantResult(success=True, response="I can adjust the room brightness.", domain="house", tool_calls=calls)

    if "light" in text:
        desired = "off" if "off" in text else "on"
        calls = [ToolCall(name="set_light", args={"room": room, "state": desired}, risk=ToolRiskLevel.LOW)]
        return AssistantResult(success=True, response="I can update the room lights.", domain="house", tool_calls=calls)

    return AssistantResult(success=False, response="I could not map that to a house plan yet.", domain="house")


def find_room(text: str) -> str:
    for room in ROOMS:
        if room in text:
            return room.replace(" ", "_")
    return "living_room"


def find_brightness(text: str) -> int:
    match = re.search(r"(\d{1,3})", text)
    if match:
        return max(0, min(100, int(match.group(1))))
    return 30 if "dim" in text else 100
