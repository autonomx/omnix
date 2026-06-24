from __future__ import annotations

from app.rpg.env_scene_intro import build_env_scene_intro_request


def test_phase29_scene_intro_request_from_environmental_trigger() -> None:
    request = build_env_scene_intro_request(
        {
            "new_game": True,
            "location": {"id": "road", "region_id": "north"},
            "environment": {"sights": ["mist over the stones"]},
        }
    )

    assert request["ready"] is True
    assert request["task"] == "environmental_scene_intro"
    assert "new_game" in request["triggers"]
    assert request["contract"]


def test_phase29_scene_intro_request_skips_without_trigger() -> None:
    request = build_env_scene_intro_request({})

    assert request["ready"] is False
    assert request["triggers"] == []
