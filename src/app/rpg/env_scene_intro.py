"""Scene introduction helpers for RPG Phase 29."""

from __future__ import annotations

from collections.abc import Mapping

from app.rpg.environmental_narration_runtime import build_environmental_narration_report

ENV_SCENE_INTRO_SOURCE = "phase29_env_scene_intro_v1"


def build_env_scene_intro_request(turn_result: Mapping[str, object]) -> dict[str, object]:
    report = build_environmental_narration_report(turn_result)
    active = bool(report.get("should_generate"))
    return {
        "source": ENV_SCENE_INTRO_SOURCE,
        "ready": active,
        "task": "environmental_scene_intro",
        "contract": report.get("scene_introduction_contract"),
        "triggers": list(report.get("triggers") or ()),
    }
