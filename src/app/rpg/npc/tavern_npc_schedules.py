from __future__ import annotations

from typing import List

from app.rpg.npc.npc_schedule import NPCScheduleBlock


def tavern_npc_ids() -> List[str]:
    return [
        "npc:bran",
        "npc:garran",
        "npc:sera",
    ]


def tavern_npc_schedule_blocks() -> List[NPCScheduleBlock]:
    return [
        NPCScheduleBlock(
            npc_id="npc:bran",
            location_id="scene:rusty_flagon",
            start_hour=6,
            end_hour=23,
            activity="tending the Rusty Flagon",
            availability="available",
            priority=10,
        ),
        NPCScheduleBlock(
            npc_id="npc:bran",
            location_id="room:bran_private_room",
            start_hour=23,
            end_hour=6,
            activity="resting after closing",
            availability="unavailable",
            priority=10,
        ),
        NPCScheduleBlock(
            npc_id="npc:garran",
            location_id="region:mill_road",
            start_hour=6,
            end_hour=14,
            activity="patrolling the mill road",
            availability="available",
            priority=10,
        ),
        NPCScheduleBlock(
            npc_id="npc:garran",
            location_id="scene:rusty_flagon",
            start_hour=14,
            end_hour=22,
            activity="watching for trouble at the tavern",
            availability="available",
            priority=10,
        ),
        NPCScheduleBlock(
            npc_id="npc:garran",
            location_id="room:garran_bunk",
            start_hour=22,
            end_hour=6,
            activity="resting between patrols",
            availability="unavailable",
            priority=10,
        ),
        NPCScheduleBlock(
            npc_id="npc:sera",
            location_id="market:lane",
            start_hour=7,
            end_hour=15,
            activity="trading and listening for rumors",
            availability="available",
            priority=10,
        ),
        NPCScheduleBlock(
            npc_id="npc:sera",
            location_id="scene:rusty_flagon",
            start_hour=15,
            end_hour=21,
            activity="sharing rumors at the tavern",
            availability="available",
            priority=10,
        ),
        NPCScheduleBlock(
            npc_id="npc:sera",
            location_id="room:sera_lodging",
            start_hour=21,
            end_hour=7,
            activity="keeping out of sight",
            availability="unavailable",
            priority=10,
        ),
    ]