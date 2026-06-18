from __future__ import annotations

from typing import Any

from app.rpg.session import loadout
from app.rpg.session.equipment import build_equipment_derived_stats, equip_item_for_player, resolve_equipment_slot


def test_equipment_slot_resolution_prefers_explicit_slot() -> None:
    assert resolve_equipment_slot({"name": "Court Signet", "slot": "Ring"}) == "Ring"
    assert resolve_equipment_slot({"name": "Practice Staff", "item_type": "tool", "slot": "Weapon"}) == "Weapon"
    assert resolve_equipment_slot({"name": "Travel Coat", "item_type": "armor"}) == "Armor"


def test_equipment_derived_stats_sum_profiles_and_modifiers() -> None:
    summary = build_equipment_derived_stats(
        [
            {
                "slot": "Weapon",
                "name": "Practice Staff",
                "item_id": "practice_staff",
                "damage": {"arcane": 6},
                "modifiers": {"initiative_modifier": 1, "archery": 2},
            },
            {
                "slot": "Armor",
                "name": "Travel Coat",
                "item_id": "travel_coat",
                "defense": {"slashing": 2, "piercing": 1},
                "resistances": {"cold": 1},
                "stats": {"stealth_modifier": 1},
            },
        ]
    )

    assert summary["damage_profile"] == {"arcane": 6}
    assert summary["defense_profile"] == {"slashing": 2, "piercing": 1}
    assert summary["resistances"] == {"cold": 1}
    assert summary["initiative_modifier"] == 1
    assert summary["stealth_modifier"] == 1
    assert summary["skill_modifiers"] == {"archery": 2}
    assert summary["sources"] == [
        {"slot": "Weapon", "name": "Practice Staff", "item_id": "practice_staff"},
        {"slot": "Armor", "name": "Travel Coat", "item_id": "travel_coat"},
    ]


def test_equip_item_for_player_replaces_slot_and_preserves_minimal_legacy_entry() -> None:
    player: dict[str, Any] = {"equipment": [{"slot": "Weapon", "name": "Old Tool"}]}

    slot, derived = equip_item_for_player(player, {"id": "simple_tool", "name": "Simple tool", "item_type": "tool", "type": "tool", "slot": "Weapon"})

    assert slot == "Weapon"
    assert player["equipment"] == [{"slot": "Weapon", "name": "Simple tool"}]
    assert derived["damage_profile"] == {}
    assert player["derived_stats"] == derived


def test_loadout_equip_updates_derived_stats(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    session = {
        "manifest": {"id": "rpg_equipment_test", "session_id": "rpg_equipment_test", "title": "Test", "updated_at": "before"},
        "state": {
            "session_id": "rpg_equipment_test",
            "current_turn": 0,
            "turn_count": 0,
            "world": {"time": "Day 1 • 08:00"},
            "player": {
                "name": "Test Hero",
                "resources": {},
                "inventory": [
                    {
                        "id": "practice_staff",
                        "item_id": "practice_staff",
                        "name": "Practice Staff",
                        "item_type": "tool",
                        "type": "tool",
                        "slot": "Weapon",
                        "damage": {"arcane": 6},
                        "modifiers": {"initiative_modifier": 1, "archery": 2},
                    }
                ],
                "equipment": [],
            },
            "timeline": [],
            "journal": {"entries": []},
        },
    }
    monkeypatch.setattr(loadout, "load_session", lambda session_id: session)
    monkeypatch.setattr(loadout, "save_session", lambda updated, *, compact=False: saved.append(updated) or updated)

    result = loadout.apply_loadout_action("rpg_equipment_test", loadout.RpgLoadoutActionRequest(action="equip", item_name="Practice Staff"))

    assert result["ok"] is True
    state = saved[0]["state"]
    assert state["player"]["equipment"][0]["slot"] == "Weapon"
    assert state["player"]["equipment"][0]["damage"] == {"arcane": 6}
    assert state["player"]["derived_stats"]["damage_profile"] == {"arcane": 6}
    assert state["player"]["derived_stats"]["initiative_modifier"] == 1
    assert state["player"]["derived_stats"]["skill_modifiers"] == {"archery": 2}
    assert state["timeline"][0]["title"] == "Equipped Practice Staff"
