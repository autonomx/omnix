from __future__ import annotations

from typing import List

from app.rpg.story.followup_arc_resolution import FollowupArcResolutionRule


def tavern_followup_resolution_rules() -> List[FollowupArcResolutionRule]:
    return [
        FollowupArcResolutionRule(
            id="resolve:sable_chain_route_pressure",
            arc_id="arc:sable_chain_route_pressure",
            from_stage="chain_notices_missing_scouts",
            outcome="route_pressure_escalated",
            status="completed",
            requires_turns_since_progress=4,
            requires_faction_tier=("faction:sable_chain", "suspicious"),
            reward_xp=5,
            set_flags=("followup:sable_chain_route_pressure.resolved",),
            world_signals=(
                {
                    "id": "signal:sable_chain_route_pressure_resolved",
                    "kind": "faction_pressure",
                    "scope": "region:mill_road",
                    "summary": "The Sable Chain shifts from missing scouts to active route pressure.",
                    "ttl_turns": 45,
                    "intensity": 3,
                    "faction_id": "faction:sable_chain",
                },
            ),
            faction_deltas=(
                {
                    "faction_id": "faction:sable_chain",
                    "delta": -1,
                    "reason": "Route pressure escalated after the scouts disappeared.",
                },
            ),
            escalation_hooks=(
                {
                    "id": "hook:sable_chain_handler",
                    "kind": "escalation_arc_seed",
                    "arc_id": "arc:sable_chain_handler",
                    "summary": "A Sable Chain handler begins coordinating pressure against the party.",
                    "priority": 4,
                },
            ),
            summary="The Sable Chain route-pressure thread resolves into a handler escalation.",
        ),
        FollowupArcResolutionRule(
            id="resolve:marked_coin_backer_trace",
            arc_id="arc:marked_coin_backer_trace",
            from_stage="backer_trace_identified",
            outcome="voss_backer_trace_resolved",
            status="completed",
            requires_turns_since_progress=4,
            requires_faction_tier=("faction:rusty_flagon_locals", "friendly"),
            reward_xp=5,
            set_flags=("followup:marked_coin_backer_trace.resolved",),
            world_signals=(
                {
                    "id": "signal:voss_name_surfaces",
                    "kind": "rumor",
                    "scope": "scene:rusty_flagon",
                    "summary": "The name Voss starts surfacing around the marked coin trail.",
                    "ttl_turns": 45,
                    "intensity": 3,
                    "faction_id": "faction:rusty_flagon_locals",
                },
            ),
            faction_deltas=(
                {
                    "faction_id": "faction:rusty_flagon_locals",
                    "delta": 1,
                    "reason": "The party developed the marked coin lead into a backer trace.",
                },
            ),
            escalation_hooks=(
                {
                    "id": "hook:voss_backer_pressure",
                    "kind": "escalation_arc_seed",
                    "arc_id": "arc:voss_backer_pressure",
                    "summary": "The Voss backer lead becomes a more dangerous investigation.",
                    "priority": 4,
                },
            ),
            summary="The marked coin backer trace resolves into the Voss investigation.",
        ),
    ]