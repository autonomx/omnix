from __future__ import annotations

from typing import List

from app.rpg.npc.npc_reaction_policy import NPCReactionRule


def tavern_npc_reaction_rules() -> List[NPCReactionRule]:
    return [
        NPCReactionRule(
            id="npc_reaction:bran_warns_after_sable_retaliation",
            npc_id="npc:bran",
            reaction_kind="warns_about_retaliation",
            required_location_id="scene:rusty_flagon",
            required_consequence_kind="retaliation_after_combat",
            cooldown_turns=20,
            event={
                "summary": "Bran warns that retaliation will not stay on the road forever.",
            },
            memory_event={
                "summary": "Bran remembers warning the party after Sable Chain retaliation escalated.",
                "importance": 2,
            },
            world_signal={
                "id": "signal:bran_reacts_to_retaliation",
                "scope": "scene:rusty_flagon",
                "summary": "Bran grows wary after signs of Sable Chain retaliation.",
            },
        ),
        NPCReactionRule(
            id="npc_reaction:garran_arms_locals_after_rally",
            npc_id="npc:garran",
            reaction_kind="arms_locals",
            required_location_id="scene:rusty_flagon",
            required_consequence_kind="locals_rally_after_combat",
            cooldown_turns=24,
            event={
                "summary": "Garran starts organizing tavern regulars into a rough watch.",
            },
            memory_event={
                "summary": "Garran remembers organizing locals after the party survived combat.",
                "importance": 2,
            },
            world_signal={
                "id": "signal:garran_arms_locals",
                "scope": "scene:rusty_flagon",
                "summary": "Garran begins organizing regulars into a rough watch.",
            },
        ),
        NPCReactionRule(
            id="npc_reaction:sera_tracks_voss_pressure",
            npc_id="npc:sera",
            reaction_kind="tracks_voss_pressure",
            required_location_id="scene:rusty_flagon",
            required_consequence_kind="backer_pressure_after_name_spread",
            cooldown_turns=24,
            event={
                "summary": "Sera starts watching who repeats the Voss name too carefully.",
            },
            memory_event={
                "summary": "Sera remembers tracking careful reactions to Voss pressure.",
                "importance": 2,
            },
            world_signal={
                "id": "signal:sera_tracks_voss_pressure",
                "scope": "scene:rusty_flagon",
                "summary": "Sera watches who repeats the Voss name too carefully.",
            },
        ),
    ]