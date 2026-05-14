from __future__ import annotations

from typing import List

from app.rpg.factions.faction_consequence_policy import FactionConsequenceRule


def tavern_faction_consequence_rules() -> List[FactionConsequenceRule]:
    return [
        FactionConsequenceRule(
            id="faction_consequence:sable_chain_retaliates_after_defeat",
            faction_id="faction:sable_chain",
            consequence_kind="retaliation_after_combat",
            required_tier="suspicious",
            required_arc_stage=("arc:sable_chain_handler", "handler_assigns_watchers"),
            required_combat_outcome="victory",
            cooldown_turns=24,
            severity=2,
            reputation_delta=-1,
            event={
                "summary": "The Sable Chain hardens its posture after losing a probe.",
            },
            world_signal={
                "id": "signal:sable_chain_retaliation_posture",
                "scope": "region:mill_road",
                "summary": "The Sable Chain tightens its posture after a failed probe.",
            },
            set_flags=("faction_consequence:sable_chain_retaliation_active",),
        ),
        FactionConsequenceRule(
            id="faction_consequence:locals_rally_after_victory",
            faction_id="faction:rusty_flagon_locals",
            consequence_kind="locals_rally_after_combat",
            required_tier="friendly",
            required_combat_outcome="victory",
            cooldown_turns=30,
            severity=1,
            reputation_delta=1,
            event={
                "summary": "Rusty Flagon locals become more willing to help after the party survives violence.",
            },
            world_signal={
                "id": "signal:locals_rally_after_combat",
                "scope": "scene:rusty_flagon",
                "summary": "Locals rally after hearing the party survived a dangerous fight.",
            },
            set_flags=("faction_consequence:locals_rallied",),
        ),
        FactionConsequenceRule(
            id="faction_consequence:voss_backers_apply_pressure",
            faction_id="faction:voss_backers",
            consequence_kind="backer_pressure_after_name_spread",
            required_arc_stage=("arc:voss_backer_pressure", "voss_name_draws_attention"),
            required_signal_kind="combat_consequence",
            cooldown_turns=30,
            severity=2,
            reputation_delta=-1,
            event={
                "summary": "Voss-linked backers apply pressure after the name draws public attention.",
            },
            world_signal={
                "id": "signal:voss_backers_apply_pressure",
                "scope": "scene:rusty_flagon",
                "summary": "Voss-linked backers apply pressure as the name spreads.",
            },
            set_flags=("faction_consequence:voss_backer_pressure_active",),
        ),
    ]