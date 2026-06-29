from __future__ import annotations

import uuid
from typing import Any

from .core import ToolCall, ToolResult
from .house_state import load_house_state, normalize_room, require_room, save_house_state


def apply_house_mock(call: ToolCall, *, dry_run: bool = False) -> ToolResult:
    state = load_house_state()
    name = call.name
    args: dict[str, Any] = call.args

    if name == "get_house_status":
        return ToolResult(name=name, ok=True, output={"state": state}, executed=False)

    if name == "set_light":
        room_key = normalize_room(str(args.get("room", "")))
        target = str(args.get("state", "on")).strip().lower()
        if target not in {"on", "off"}:
            raise ValueError("invalid_light_state")
        room = require_room(state, room_key)
        if not dry_run:
            room["lights"] = target
            save_house_state(state)
        return ToolResult(name=name, ok=True, output={"room": room_key, "state": target}, executed=not dry_run)

    if name == "set_brightness":
        room_key = normalize_room(str(args.get("room", "")))
        brightness = int(args.get("brightness", 100))
        if not 0 <= brightness <= 100:
            raise ValueError("brightness_out_of_range")
        room = require_room(state, room_key)
        if not dry_run:
            room["brightness"] = brightness
            save_house_state(state)
        return ToolResult(name=name, ok=True, output={"room": room_key, "brightness": brightness}, executed=not dry_run)

    raise ValueError(f"unknown_house_mock:{name}")
