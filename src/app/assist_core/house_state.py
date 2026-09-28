from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.runtime.paths import resources_data_root

DEFAULT_HOUSE_STATE = {
    "rooms": {
        "kitchen": {"lights": "off", "brightness": 100},
        "living_room": {"lights": "off", "brightness": 100},
        "bedroom": {"lights": "off", "brightness": 100},
        "office": {"lights": "off", "brightness": 100},
    },
    "thermostat": {"temperature_c": 21},
    "reminders": [],
}


def assist_data_root() -> Path:
    path = resources_data_root() / "assist_core"
    path.mkdir(parents=True, exist_ok=True)
    return path


def house_state_path() -> Path:
    return assist_data_root() / "mock_house_state.json"


def load_house_state() -> dict[str, Any]:
    from app.persistence.runtime import uses_postgresql_runtime
    if uses_postgresql_runtime():
        from app.assist_core.persistence.house_state import load_house_state_postgres
        return load_house_state_postgres()
    path = house_state_path()
    if not path.exists():
        save_house_state(DEFAULT_HOUSE_STATE)
        return json.loads(json.dumps(DEFAULT_HOUSE_STATE))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(DEFAULT_HOUSE_STATE))


def save_house_state(state: dict[str, Any]) -> None:
    from app.persistence.runtime import uses_postgresql_runtime
    if uses_postgresql_runtime():
        from app.assist_core.persistence.house_state import save_house_state_postgres
        return save_house_state_postgres(state)
    house_state_path().write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def normalize_room(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def require_room(state: dict[str, Any], room_name: str) -> dict[str, Any]:
    room_key = normalize_room(room_name)
    rooms = state.setdefault("rooms", {})
    if room_key not in rooms:
        raise ValueError(f"unknown_room:{room_key}")
    return rooms[room_key]
