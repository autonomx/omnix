from __future__ import annotations

from typing import List

from app.rpg.story.followup_arc_progression import FollowupArcProgressionRule


def tavern_followup_progression_rules() -> List[FollowupArcProgressionRule]:
    return [
        FollowupArcProgressionRule(
            id="followup:route_pressure_notice",
            arc_id="arc:sable_chain_route_pressure",
            from_stage="seeded_followup",
            to_stage="chain_notices_missing_scouts",
            requires_turns_since_started=3,
            requires_faction_tier=("faction:sable_chain", "suspicious"),
            set_flags=("followup:sable_chain_route_pressure.progressed",),
            world_signals=(
                {
                    "id": "signal:sable_chain_missing_scouts",
                    "kind": "faction_pressure",
                    "scope": "region:mill_road",
                    "summary": "The Sable Chain notices that its scouts near the old mill failed to report back.",
                    "ttl_turns": 40,
                    "intensity": 3,
                    "faction_id": "faction:sable_chain",
                },
            ),
            followup_hooks=(
                {
                    "id": "hook:sable_chain_watchers",
                    "kind": "pressure_escalation",
                    "arc_id": "arc:sable_chain_watchers",
                    "summary": "Sable Chain watchers may begin tracking the party.",
                    "priority": 2,
                },
            ),
            summary="The Sable Chain notices the missing scouts and begins watching the road.",
        ),
        FollowupArcProgressionRule(
            id="followup:marked_coin_backer_trace",
            arc_id="arc:marked_coin_backer_trace",
            from_stage="seeded_followup",
            to_stage="backer_trace_identified",
            requires_turns_since_started=2,
            requires_faction_tier=("faction:rusty_flagon_locals", "friendly"),
            set_flags=("followup:marked_coin_backer_trace.progressed",),
            world_signals=(
                {
                    "id": "signal:marked_coin_backer_whisper",
                    "kind": "rumor",
                    "scope": "scene:rusty_flagon",
                    "summary": "A local whisper suggests the marked coin came through a paid backer, not the scouts themselves.",
                    "ttl_turns": 35,
                    "intensity": 2,
                    "faction_id": "faction:rusty_flagon_locals",
                },
            ),
            followup_hooks=(
                {
                    "id": "hook:voss_backer_investigation",
                    "kind": "followup_arc_seed",
                    "arc_id": "arc:voss_backer_investigation",
                    "summary": "The marked coin trail points toward a backer named Voss.",
                    "priority": 3,
                },
            ),
            summary="Local trust turns the marked coin into a backer lead.",
        ),
    ]