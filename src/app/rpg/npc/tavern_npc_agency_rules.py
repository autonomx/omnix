from __future__ import annotations

from typing import List

from app.rpg.npc.npc_agency import NPCAgencyRule


def tavern_npc_agency_rules() -> List[NPCAgencyRule]:
    return [
        NPCAgencyRule(
            id="agency:garran_tracks_handler_watchers",
            npc_id="npc:garran",
            required_location_id="region:mill_road",
            required_arc_stage=("arc:sable_chain_handler", "handler_assigns_watchers"),
            required_faction_tier=("faction:sable_chain", "suspicious"),
            cooldown_turns=18,
            event={
                "summary": "Garran adjusts his patrol after signs of Sable Chain watchers.",
                "severity": 2,
            },
            world_signal={
                "id": "signal:garran_patrol_adjusts",
                "kind": "npc_agency",
                "scope": "region:mill_road",
                "summary": "Garran shifts his patrol pattern to watch for Sable Chain scouts.",
                "ttl_turns": 50,
                "intensity": 2,
            },
            memory_event={
                "kind": "npc_memory",
                "summary": "Garran remembers adjusting his patrols after watcher signs appeared.",
                "importance": 2,
            },
            set_flags=("npc_agency:garran_patrol_adjusted",),
        ),
        NPCAgencyRule(
            id="agency:sera_tests_voss_rumor",
            npc_id="npc:sera",
            required_location_id="scene:rusty_flagon",
            required_arc_stage=("arc:voss_backer_pressure", "voss_name_draws_attention"),
            required_faction_tier=("faction:rusty_flagon_locals", "friendly"),
            cooldown_turns=18,
            event={
                "summary": "Sera quietly tests the Voss rumor among tavern regulars.",
                "severity": 1,
            },
            world_signal={
                "id": "signal:sera_tests_voss_rumor",
                "kind": "npc_agency",
                "scope": "scene:rusty_flagon",
                "summary": "Sera tests who reacts to the name Voss.",
                "ttl_turns": 50,
                "intensity": 2,
            },
            memory_event={
                "kind": "npc_memory",
                "summary": "Sera remembers who grew cautious when Voss was mentioned.",
                "importance": 2,
            },
            set_flags=("npc_agency:sera_tested_voss_rumor",),
        ),
        NPCAgencyRule(
            id="agency:bran_warns_about_pressure",
            npc_id="npc:bran",
            required_location_id="scene:rusty_flagon",
            required_faction_tier=("faction:sable_chain", "suspicious"),
            cooldown_turns=24,
            event={
                "summary": "Bran warns regulars to keep trouble outside the Rusty Flagon.",
                "severity": 1,
            },
            world_signal={
                "id": "signal:bran_warns_regulars",
                "kind": "npc_agency",
                "scope": "scene:rusty_flagon",
                "summary": "Bran warns regulars that Sable Chain trouble should stay outside.",
                "ttl_turns": 40,
                "intensity": 1,
            },
            memory_event={
                "kind": "npc_memory",
                "summary": "Bran remembers warning regulars after Sable Chain pressure rose.",
                "importance": 1,
            },
            set_flags=("npc_agency:bran_warned_regulars",),
        ),
    ]