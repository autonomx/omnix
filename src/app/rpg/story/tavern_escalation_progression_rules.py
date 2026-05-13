from __future__ import annotations

from typing import List

from app.rpg.story.escalation_arc_progression import EscalationArcProgressionRule


def tavern_escalation_progression_rules() -> List[EscalationArcProgressionRule]:
    return [
        EscalationArcProgressionRule(
            id="escalation:sable_chain_handler_moves",
            arc_id="arc:sable_chain_handler",
            from_stage="seeded_escalation",
            to_stage="handler_assigns_watchers",
            requires_turns_since_started=3,
            requires_faction_tier=("faction:sable_chain", "suspicious"),
            set_flags=("escalation:sable_chain_handler.progressed",),
            world_signals=(
                {
                    "id": "signal:sable_chain_handler_watchers",
                    "kind": "faction_pressure",
                    "scope": "region:mill_road",
                    "summary": "A Sable Chain handler assigns watchers to learn who disrupted the old mill route.",
                    "ttl_turns": 60,
                    "intensity": 4,
                    "faction_id": "faction:sable_chain",
                },
            ),
            pressure_events=(
                {
                    "type": "faction_pressure",
                    "subtype": "handler_watchers",
                    "faction_id": "faction:sable_chain",
                    "summary": "A handler coordinates watchers along the road.",
                    "severity": 3,
                },
            ),
            summary="The Sable Chain handler begins coordinating watchers.",
        ),
        EscalationArcProgressionRule(
            id="escalation:voss_backer_pressure",
            arc_id="arc:voss_backer_pressure",
            from_stage="seeded_escalation",
            to_stage="voss_name_draws_attention",
            requires_turns_since_started=3,
            requires_faction_tier=("faction:rusty_flagon_locals", "friendly"),
            set_flags=("escalation:voss_backer_pressure.progressed",),
            world_signals=(
                {
                    "id": "signal:voss_backer_attention",
                    "kind": "rumor",
                    "scope": "scene:rusty_flagon",
                    "summary": "The name Voss draws cautious attention among the Rusty Flagon locals.",
                    "ttl_turns": 60,
                    "intensity": 3,
                    "faction_id": "faction:rusty_flagon_locals",
                },
            ),
            pressure_events=(
                {
                    "type": "faction_pressure",
                    "subtype": "voss_backer_attention",
                    "faction_id": "faction:rusty_flagon_locals",
                    "summary": "Locals become careful when Voss is mentioned.",
                    "severity": 2,
                },
            ),
            summary="The Voss backer thread begins drawing attention.",
        ),
    ]