from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_legacy_gateway_response_bridge_and_duplicate_route_are_deleted() -> None:
    gateway = _REPO_ROOT / "src" / "app" / "composition" / "gateway"

    assert not (gateway / "rpg_visible_response_bridge.py").exists()
    assert not (gateway / "rpg_direct_turn_routes.py").exists()
