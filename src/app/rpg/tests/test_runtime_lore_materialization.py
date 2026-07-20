from __future__ import annotations

from app.rpg.interactions.interaction_runtime import resolve_general_interaction
from app.rpg.session.genesis.runtime_materialization import (
    CreatureDefinition,
    CreatureVulnerability,
    RuntimeMaterializationProposal,
    apply_runtime_materialization,
)


def _lore_text(name: str) -> str:
    return "\n\n".join(
        [
            f"{name} moves through the rain-dark woodland as though it were following a road no mortal eye can see. "
            "Its grey coat catches stray light in pale ripples, while every footprint fades into a thin curl of mist. "
            "Hunters know it first by the sudden silence of birds and by a doubled howl that seems to arrive from behind the listener.",
            "The creature feeds on memories sharpened by fear. It circles isolated travelers, repeating fragments of familiar voices until "
            "someone leaves the safety of firelight. It avoids settled roads at noon, but old bridges, ruined shrines, and moonlit riverbanks "
            "offer it places where echoes linger. Patient packs will test a camp for hours before one wolf commits to an attack.",
            "Clear bronze bells disrupt the resonance holding its body together. A bell rung close enough forces the beast into solid form, "
            "leaving it stunned and vulnerable for a precious moment. Villages therefore hang small bells above sheepfolds and western doors, "
            "though cracked iron bells merely anger the wolves. Survivors insist the distinction matters more than courage.",
            "Scholars disagree over whether these beasts are animals changed by Aurelia or memories that learned to hunt. Their dens contain no "
            "bones, only weathered keepsakes gathered from missing travelers. Destroying such objects can scatter a pack, but returning one to "
            "its rightful family has sometimes caused a wolf to bow its head and disappear without violence.",
        ]
    )


def _proposal(name: str = "Echo Wolf") -> RuntimeMaterializationProposal:
    return RuntimeMaterializationProposal(
        kind="creature",
        name=name,
        lore_text=_lore_text(name),
        creature=CreatureDefinition(
            definition_id="creature:echo-wolf",
            name=name,
            level=4,
            hp=38,
            defense=14,
            armor=2,
            damage_min=5,
            damage_max=9,
            accuracy_bonus=3,
            initiative_bonus=4,
            morale_threshold=25,
            tags=["beast", "echo", "memory"],
            loot_table_id="loot:echo-wolf",
            xp_value=120,
            budget_cost=90,
            condition_immunities=["prone"],
            vulnerabilities=[
                CreatureVulnerability(
                    trigger_tag="bronze bell",
                    aliases=["bell", "clear bell"],
                    condition="stunned",
                    duration_turns=1,
                    magnitude=1,
                    description="A clear bell collapses its resonant form.",
                )
            ],
            behavior="Stalks frightened targets and uses copied voices to isolate them.",
            habitat="Old bridges, memory-rich ruins, and moonlit woodland.",
        ),
    )


def test_materialization_commits_lore_and_versioned_mechanics_together() -> None:
    bible = {
        "documents": [],
        "entities": {},
        "retrieval_cards": [],
        "discovery_state": {"pages": {}, "entities": {}, "discoveries": []},
        "manifest": {},
    }

    first, document_id, definition = apply_runtime_materialization(
        bible,
        _proposal(),
        canon_revision=7,
    )

    assert document_id == "lore:runtime:creature:echo-wolf"
    assert first["canon_revision"] == 7
    assert first["documents"][0]["full_text"] == _lore_text("Echo Wolf")
    assert first["documents"][0]["provenance"] == {
        "source": "runtime_structured_materialization",
        "definition_id": "creature:echo-wolf",
        "definition_revision": 1,
    }
    assert definition["definition_revision"] == 1
    assert first["mechanics_catalog"]["creatures"]["creature:echo-wolf"] == definition
    assert first["discovery_state"]["pages"][document_id] == "learned"
    assert len(first["retrieval_cards"]) == 2

    second, same_document_id, rebuilt = apply_runtime_materialization(
        first,
        _proposal(),
        canon_revision=8,
        requested_document_id=document_id,
    )

    assert same_document_id == document_id
    assert rebuilt["definition_revision"] == 2
    assert len(second["documents"]) == 1
    assert len(second["retrieval_cards"]) == 2
    assert second["documents"][0]["provenance"]["definition_revision"] == 2


def test_compiled_creature_drives_encounter_and_lore_weakness() -> None:
    state = {
        "session_id": "campaign:test",
        "hp": 20,
        "max_hp": 20,
        "player_state": {
            "party_state": {"companions": []},
            "inventory": {
                "items": [
                    {
                        "item_id": "item:bronze-bell",
                        "name": "bronze bell",
                        "aliases": ["bell", "clear bell"],
                    }
                ]
            },
        },
        "campaign_mechanics": {
            "schema_version": "rpg_campaign_mechanics_v1",
            "creatures": {
                "creature:echo-wolf": _proposal().creature.model_dump(mode="json")
            },
            "locations": {},
        },
    }

    started = resolve_general_interaction(
        state,
        player_input="attack the Echo Wolf",
        tick=1,
    )

    assert started["combat_result"]["reason"] == "combat_started"
    enemies = [
        row
        for row in state["combat_state"]["participants"].values()
        if row["side"] == "enemy"
    ]
    assert len(enemies) == 1
    assert enemies[0]["name"] == "Echo Wolf"
    assert enemies[0]["hp"] == 38
    assert enemies[0]["definition_id"] == "creature:echo-wolf"
    assert enemies[0]["definition_revision"] == 1

    initiative = state["combat_state"]["initiative_order"]
    state["combat_state"]["turn_index"] = next(
        index for index, row in enumerate(initiative) if row["actor_id"] == "player"
    )
    state["combat_state"]["current_actor_id"] = "player"

    bell = state["player_state"]["inventory"]["items"].pop()
    blocked = resolve_general_interaction(
        state,
        player_input="use the bronze bell on the Echo Wolf",
        tick=2,
    )
    assert blocked["interaction_result"]["reason"] == (
        "vulnerability_trigger_item_not_available"
    )
    state["player_state"]["inventory"]["items"].append(bell)

    triggered = resolve_general_interaction(
        state,
        player_input="use the bronze bell on the Echo Wolf",
        tick=3,
    )

    assert triggered["interaction_result"]["reason"] == "campaign_vulnerability_triggered"
    target_id = triggered["vulnerability_result"]["target_id"]
    effects = state["combat_state"]["participants"][target_id]["status_effects"]
    assert effects == []
    assert state["combat_state"]["pending_skip_turn_actor_id"] == target_id
    assert state["combat_state"]["last_condition_result"]["reason"] == (
        "stunned_skip_turn"
    )
    assert state["combat_state"]["last_vulnerability_result"]["definition_revision"] == 1
    assert triggered["turn_result"]["reason"] == "combat_turn_advanced"
