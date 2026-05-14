from __future__ import annotations

from typing import List

from app.rpg.combat.combat_lifecycle import CombatEncounterRule


def tavern_combat_lifecycle_rules() -> List[CombatEncounterRule]:
    return [
        CombatEncounterRule(
            id="combat:sable_chain_road_probe",
            encounter_id="encounter:sable_chain_road_probe",
            trigger_every_turns=28,
            required_arc_stage=("arc:sable_chain_handler", "handler_assigns_watchers"),
            required_faction_tier=("faction:sable_chain", "suspicious"),
            enemy_id="enemy:sable_chain_probe",
            enemy_name="Sable Chain Probe",
            enemy_hp=8,
            enemy_attack=2,
            player_attack=3,
            max_rounds=4,
            cooldown_turns=24,
            world_signal={
                "id": "signal:combat_sable_chain_probe",
                "scope": "region:mill_road",
                "summary": "A Sable Chain probe tests the road after watcher pressure rises.",
            },
        ),
        CombatEncounterRule(
            id="combat:voss_backer_threat",
            encounter_id="encounter:voss_backer_threat",
            trigger_every_turns=36,
            required_arc_stage=("arc:voss_backer_pressure", "voss_name_draws_attention"),
            required_faction_tier=("faction:rusty_flagon_locals", "friendly"),
            enemy_id="enemy:voss_backer_enforcer",
            enemy_name="Voss Backer Enforcer",
            enemy_hp=10,
            enemy_attack=3,
            player_attack=3,
            max_rounds=4,
            cooldown_turns=30,
            world_signal={
                "id": "signal:combat_voss_backer_threat",
                "scope": "scene:rusty_flagon",
                "summary": "A Voss-linked enforcer tries to intimidate the investigation.",
            },
        ),
    ]