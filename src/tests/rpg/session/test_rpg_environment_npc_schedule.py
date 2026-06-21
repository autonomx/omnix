from app.rpg.session.environment_npc_schedule import build_npc_schedule_environment_context


def test_indoor_scene_is_not_currently_outdoor() -> None:
    context = build_npc_schedule_environment_context({"context": {"exposure": "indoor"}})

    assert context["outdoor_activity"] == "not_currently_outdoor"
