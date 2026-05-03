from __future__ import annotations

from typing import Any, Dict

from tests.rpg.spatial.fixtures import (
    tavern_spatial_fixture,
    tavern_spatial_fixture_with_private_door_open,
)


def build_manual_spatial_fixture(name: str) -> Dict[str, Any]:
    if name == "tavern_fixture":
        return tavern_spatial_fixture()
    if name == "tavern_fixture_private_door_open":
        return tavern_spatial_fixture_with_private_door_open()
    raise KeyError(f"unknown_manual_spatial_fixture:{name}")