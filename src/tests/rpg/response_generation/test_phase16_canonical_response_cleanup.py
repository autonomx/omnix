from __future__ import annotations

from pathlib import Path

from app.jobs import inline_feature_jobs
from app.rpg.presentation.visible_response import visible_response_text

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
    assert inline_feature_jobs._rpg_turn_visible_text(result) == expected


def test_legacy_gateway_response_bridge_and_duplicate_route_are_deleted() -> None:
    gateway = _REPO_ROOT / "src" / "app" / "gateway"

    assert not (gateway / "rpg_visible_response_bridge.py").exists()
    assert not (gateway / "rpg_direct_turn_routes.py").exists()


def test_gateway_and_job_guards_do_not_patch_visible_formatters() -> None:
    gateway_init = (_REPO_ROOT / "src" / "app" / "gateway" / "__init__.py").read_text(encoding="utf-8")
    mirror = (_REPO_ROOT / "src" / "app" / "gateway" / "rpg_turn_job_mirror.py").read_text(encoding="utf-8")
    session_routes = (_REPO_ROOT / "src" / "app" / "gateway" / "rpg_session_routes.py").read_text(encoding="utf-8")
    job_guard = (_REPO_ROOT / "src" / "app" / "jobs" / "rpg_turn_job_guard.py").read_text(encoding="utf-8")

    assert "rpg_visible_response_bridge" not in gateway_init
    assert "_visible_turn_text" not in mirror
    assert "_foreground_turn_text" not in session_routes
    assert "_patch_rpg_turn_visible_formatter" not in job_guard
    assert "visible_response_text(result, command)" in mirror
