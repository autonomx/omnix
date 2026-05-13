from app.rpg.npc.npc_schedule import NPCScheduleBlock, resolve_npc_schedule_state


def test_npc_schedule_resolves_location_by_hour():
    result = resolve_npc_schedule_state(
        npc_ids=["npc:test"],
        schedule_blocks=[
            NPCScheduleBlock(
                npc_id="npc:test",
                location_id="scene:day",
                start_hour=8,
                end_hour=20,
                activity="working",
            ),
            NPCScheduleBlock(
                npc_id="npc:test",
                location_id="scene:night",
                start_hour=20,
                end_hour=8,
                activity="resting",
            ),
        ],
        turn_index=1,
        minutes_per_turn=60,
        start_hour=8,
    )

    assert result["presence"]["npc:test"]["location_id"] == "scene:day"

    night = resolve_npc_schedule_state(
        npc_ids=["npc:test"],
        schedule_blocks=[
            NPCScheduleBlock(
                npc_id="npc:test",
                location_id="scene:day",
                start_hour=8,
                end_hour=20,
                activity="working",
            ),
            NPCScheduleBlock(
                npc_id="npc:test",
                location_id="scene:night",
                start_hour=20,
                end_hour=8,
                activity="resting",
            ),
        ],
        turn_index=13,
        minutes_per_turn=60,
        start_hour=8,
        previous_presence=result["presence"],
    )

    assert night["presence"]["npc:test"]["location_id"] == "scene:night"
    assert night["movement_events"]