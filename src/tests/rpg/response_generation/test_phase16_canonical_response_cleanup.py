from __future__ import annotations

from pathlib import Path

from app.apps.rpg.session.jobs import turn_executor
from app.apps.rpg.narration.presentation.visible_response import visible_response_text

_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_all_delivery_paths_share_canonical_visible_text() -> None:
    result = {
        "player_input": "I ask Bran how business is going.",
        "narration": "Bran glances across the common room before answering.",
        "npc": {
            "speaker_id": "npc:bran",
            "speaker": "Bran",
            "line": "Steady enough. The road has been quieter than usual.",
        },
    }

    expected = visible_response_text(result, result["player_input"])

    assert expected
    assert turn_executor._rpg_turn_visible_text(result) == expected


def test_legacy_gateway_response_bridge_and_duplicate_route_are_deleted() -> None:
    gateway = _REPO_ROOT / "src" / "app" / "composition" / "gateway"

    assert not (gateway / "rpg_visible_response_bridge.py").exists()
    assert not (gateway / "rpg_direct_turn_routes.py").exists()
