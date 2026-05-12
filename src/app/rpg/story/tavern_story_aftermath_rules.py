from __future__ import annotations

from typing import List

from app.rpg.story.story_arc_aftermath import ArcAftermathRule


def tavern_story_aftermath_rules() -> List[ArcAftermathRule]:
    return [
        ArcAftermathRule(
            id="aftermath:mill_road_threat_completed",
            arc_id="arc:mill_road_threat",
            outcome="completed_bandit_scout_threat",
            on_status="completed",
            set_flags=("aftermath:mill_road_secured",),
            world_signals=(
                {
                    "id": "signal:mill_road_safer",
                    "kind": "security",
                    "scope": "location:old_mill",
                    "summary": "The old mill road is safer after the scouts are defeated.",
                    "ttl_turns": 40,
                    "intensity": 2,
                },
            ),
            npc_memory_events=(
                {
                    "npc_id": "npc:bran",
                    "memory_type": "gratitude",
                    "summary": "The party helped secure the road near the old mill.",
                    "importance": 3,
                },
            ),
            faction_deltas=(
                {
                    "faction_id": "faction:rusty_flagon_locals",
                    "delta": 2,
                    "reason": "Secured the old mill road.",
                },
                {
                    "faction_id": "faction:sable_chain",
                    "delta": -1,
                    "reason": "Disrupted scouts near the old mill.",
                },
            ),
            followup_hooks=(
                {
                    "id": "hook:sable_chain_route_pressure",
                    "kind": "followup_arc_seed",
                    "arc_id": "arc:sable_chain_route_pressure",
                    "summary": "Someone may notice that the old mill scouts failed to return.",
                    "priority": 2,
                },
            ),
            summary="The old mill road victory creates local gratitude and Sable Chain pressure.",
        ),
        ArcAftermathRule(
            id="aftermath:marked_coin_completed",
            arc_id="arc:marked_coin_investigation",
            outcome="completed_marked_coin_lead",
            on_status="completed",
            set_flags=("aftermath:marked_coin_reported",),
            world_signals=(
                {
                    "id": "signal:marked_coin_rumor_spreads",
                    "kind": "rumor",
                    "scope": "scene:rusty_flagon",
                    "summary": "Rumors spread that the party brought back a marked coin from the mill road.",
                    "ttl_turns": 50,
                    "intensity": 2,
                },
            ),
            npc_memory_events=(
                {
                    "npc_id": "npc:mira",
                    "memory_type": "trust",
                    "summary": "The party followed through on the marked coin lead.",
                    "importance": 3,
                },
            ),
            faction_deltas=(
                {
                    "faction_id": "faction:rusty_flagon_locals",
                    "delta": 1,
                    "reason": "Resolved the marked coin lead.",
                },
                {
                    "faction_id": "faction:sable_chain",
                    "delta": -2,
                    "reason": "Exposed a marked coin connected to the old mill scouts.",
                },
            ),
            followup_hooks=(
                {
                    "id": "hook:marked_coin_backer_trace",
                    "kind": "followup_arc_seed",
                    "arc_id": "arc:marked_coin_backer_trace",
                    "summary": "The marked coin points toward whoever backed the scouts.",
                    "priority": 3,
                },
            ),
            summary="The marked coin resolution creates a new lead toward the backers.",
        ),
    ]