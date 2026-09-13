from __future__ import annotations

from typing import Any

from app.platform import rpg_session_compat
from app.rpg.session import loadout, loadout_with_hooks


def _session() -> dict[str, Any]:
    return {
        "manifest": {"id": "rpg_test", "session_id": "rpg_test", "title": "Test", "updated_at": "before"},
        "state": {
            "session_id": "rpg_test",
            "current_turn": 0,
            "turn_count": 0,
            "world": {"time": "Day 1 • 08:00"},
            "summary": "Before",
            "player": {
                "name": "Test Hero",
                "resources": {
                    "hp": {"current": 50, "max": 100},
                    "stamina": {"current": 50, "max": 100},
                    "mana": {"current": 20, "max": 40},
                },
                "inventory": [
                    {"id": "health_potion", "name": "Health Potion", "quantity": 2, "type": "consumable"},
                    {"id": "simple_bow", "name": "Simple bow", "quantity": 1, "type": "weapon"},
                    {"id": "broken_sword", "name": "Broken Sword", "quantity": 1, "item_type": "weapon", "type": "weapon", "weapon_type": "sword"},
                    {
                        "id": "iron",
                        "item_id": "iron",
                        "name": "Iron scrap",
                        "quantity": 2,
                        "item_type": "crafting_material",
                        "type": "crafting_material",
                        "material_id": "iron",
                        "material_role": "metal",
                        "stackable": True,
                    },
                    {"id": "journal", "name": "Journal", "quantity": 1, "type": "quest"},
                ],
                "equipment": [],
            },
            "timeline": [],
            "journal": {"entries": []},
        },
    }


def test_use_health_potion_consumes_item_and_restores_hp(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    monkeypatch.setattr(loadout, "load_session", lambda session_id: _session())
    monkeypatch.setattr(loadout, "save_session", lambda session, *, compact=False: saved.append(session) or session)

    result = loadout.apply_loadout_action("rpg_test", loadout.RpgLoadoutActionRequest(action="use", item_name="Health Potion"))

    assert result["ok"] is True
    state = saved[0]["state"]
    assert state["player"]["resources"]["hp"] == {"current": 75, "max": 100}
    assert state["player"]["inventory"][0]["quantity"] == 1
    assert state["turn_count"] == 1
    assert state["timeline"][0]["kind"] == "item"
    assert result["item_hook_result"]["skipped"] is False
    assert result["item_hook_result"]["action"] == "use"
    assert state["mechanics"]["item_loadout_hook_traces"][0]["action"] == "use"


def test_equip_item_updates_equipment(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    monkeypatch.setattr(loadout, "load_session", lambda session_id: _session())
    monkeypatch.setattr(loadout, "save_session", lambda session, *, compact=False: saved.append(session) or session)

    result = loadout.apply_loadout_action("rpg_test", loadout.RpgLoadoutActionRequest(action="equip", item_name="Simple bow"))

    assert result["ok"] is True
    assert saved[0]["state"]["player"]["equipment"] == [{"slot": "Weapon", "name": "Simple bow"}]
    assert saved[0]["state"]["timeline"][0]["title"] == "Equipped Simple bow"


def test_salvage_consumes_source_merges_materials_and_writes_trace(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    monkeypatch.setattr(loadout, "load_session", lambda session_id: _session())
    monkeypatch.setattr(loadout, "save_session", lambda session, *, compact=False: saved.append(session) or session)

    result = loadout.apply_loadout_action("rpg_test", loadout.RpgLoadoutActionRequest(action="salvage", item_name="Broken Sword"))

    assert result["ok"] is True
    assert result["outputs"][0]["material_id"] == "iron"
    state = saved[0]["state"]
    inventory = state["player"]["inventory"]
    assert all(item.get("name") != "Broken Sword" for item in inventory)
    by_material = {item.get("material_id"): item for item in inventory if item.get("material_id")}
    assert by_material["iron"]["quantity"] == 5
    assert by_material["leather"]["quantity"] == 1
    assert state["turn_count"] == 1
    assert state["timeline"][0]["kind"] == "salvage"
    assert state["timeline"][0]["title"] == "Salvaged Broken Sword"
    assert state["journal"]["entries"][0]["kind"] == "salvage"
    trace = state["mechanics"]["salvage_traces"][0]
    assert trace["event"] == "item_salvaged"
    assert trace["source_item_name"] == "Broken Sword"
    assert trace["outputs"][0]["material_id"] == "iron"
    assert trace in state["mechanics"]["item_traces"]
    assert state["mechanics"]["item_loadout_hook_traces"][0]["action"] == "salvage"


def test_modify_action_consumes_material_updates_item_and_writes_trace(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    monkeypatch.setattr(loadout, "load_session", lambda session_id: _session())
    monkeypatch.setattr(loadout, "save_session", lambda session, *, compact=False: saved.append(session) or session)

    result = loadout.apply_loadout_action(
        "rpg_test",
        loadout.RpgLoadoutActionRequest(action="modify", item_name="Broken Sword", mod_id="edge_damage_minor"),
    )

    assert result["ok"] is True
    assert result["modification"] == {"mod_id": "edge_damage_minor", "name": "Honed Edge"}
    assert result["consumed_materials"] == [{"material_id": "iron", "quantity": 1, "name": "Iron scrap"}]
    state = saved[0]["state"]
    inventory = state["player"]["inventory"]
    sword = next(item for item in inventory if item.get("name") == "Broken Sword")
    iron = next(item for item in inventory if item.get("material_id") == "iron")
    assert sword["damage"] == {"slashing": 1}
    assert sword["modifications"] == [
        {"mod_id": "edge_damage_minor", "name": "Honed Edge", "mechanics_source": "engine_item_modification_v1"}
    ]
    assert iron["quantity"] == 1
    assert state["turn_count"] == 1
    assert state["timeline"][0]["kind"] == "item_modification"
    assert state["timeline"][0]["title"] == "Modified Broken Sword"
    assert state["journal"]["entries"][0]["kind"] == "item_modification"
    trace = state["mechanics"]["modification_traces"][0]
    assert trace["event"] == "item_modified"
    assert trace["mod_id"] == "edge_damage_minor"
    assert trace["consumed_materials"] == [{"material_id": "iron", "quantity": 1, "name": "Iron scrap"}]
    assert trace in state["mechanics"]["item_traces"]
    assert state["mechanics"]["item_loadout_hook_traces"][0]["action"] == "modify"


def test_modify_action_rejects_missing_materials(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    session = _session()
    session["state"]["player"]["inventory"] = [
        item for item in session["state"]["player"]["inventory"] if item.get("material_id") != "iron"
    ]
    monkeypatch.setattr(loadout, "load_session", lambda session_id: session)
    monkeypatch.setattr(loadout, "save_session", lambda updated, *, compact=False: saved.append(updated) or updated)

    result = loadout.apply_loadout_action(
        "rpg_test",
        loadout.RpgLoadoutActionRequest(action="modify", item_name="Broken Sword", mod_id="edge_damage_minor"),
    )

    assert result["ok"] is False
    assert result["error"] == "missing_modification_materials"
    assert result["missing"] == [{"material_id": "iron", "required": 1, "available": 0}]
    assert saved == []


def test_hotbar_action_spends_resource_writes_event_and_snapshots_coverage(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    monkeypatch.setattr(loadout, "load_session", lambda session_id: _session())
    monkeypatch.setattr(loadout, "save_session", lambda session, *, compact=False: saved.append(session) or session)

    result = loadout.apply_loadout_action("rpg_test", loadout.RpgLoadoutActionRequest(action="hotbar", hotbar_slot="2", target="the nearest foe"))

    assert result["ok"] is True
    state = saved[0]["state"]
    assert state["player"]["resources"]["mana"] == {"current": 8, "max": 40}
    assert state["timeline"][0]["title"] == "Used Frost Arrow"
    assert state["runtime"]["effects"][0]["source"] == "Frost Arrow"
    assert result["item_hook_result"]["skipped"] is True
    assert "item_loadout_hook_traces" not in state["mechanics"]
    snapshot = state["mechanics"]["ability_coverage_snapshots"][0]
    assert snapshot["covered_dimensions"] == ["environment", "position"]
    assert snapshot["missing_dimensions"] == ["resources", "information", "relationships", "access", "narrative", "economy", "world"]


def test_legacy_ability_backfill_uses_saved_setup_identity(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    session = _session()
    session["setup_payload"] = {
        "genre": "political_intrigue",
        "tone": "courtroom pressure",
        "player": {"background": "disgraced envoy"},
        "primary_capability": "influence",
        "secondary_capabilities": ["knowledge", "recon"],
        "power_source": "social_power",
        "generated_class_name": "Court Schemer",
        "generated_class_summary": "A saved operator of favors and leverage.",
    }
    monkeypatch.setattr(loadout, "load_session", lambda session_id: session)
    monkeypatch.setattr(loadout, "save_session", lambda updated, *, compact=False: saved.append(updated) or updated)

    result = loadout.apply_loadout_action("rpg_test", loadout.RpgLoadoutActionRequest(action="hotbar", hotbar_slot="1"))

    assert result["ok"] is True
    identity = saved[0]["state"]["character_identity"]
    assert identity["genre"] == "political_intrigue"
    assert identity["tone"] == "courtroom pressure"
    assert identity["background"] == "disgraced envoy"
    assert identity["primary_capability"] == "influence"
    assert identity["secondary_capabilities"] == ["knowledge", "recon"]
    assert identity["power_source"] == "social_power"
    assert identity["generated_class_name"] == "Court Schemer"
    assert saved[0]["state"]["ability_tree"]["primary_capability"] == "influence"


def test_unlock_ability_action_spends_ability_point(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    session = _session()
    session["state"]["player"]["level"] = 2
    monkeypatch.setattr(loadout, "load_session", lambda session_id: session)
    monkeypatch.setattr(loadout, "save_session", lambda updated, *, compact=False: saved.append(updated) or updated)

    result = loadout.apply_loadout_action("rpg_test", loadout.RpgLoadoutActionRequest(action="unlock_ability", ability_id="recon_volley"))

    assert result["ok"] is True
    state = saved[0]["state"]
    assert "recon_volley" in state["ability_state"]["unlocked"]
    assert state["ability_state"]["ability_points"] == 0
    assert state["timeline"][0]["kind"] == "ability_progression"


def test_assign_and_remove_hotbar_actions_update_session(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    session = _session()
    monkeypatch.setattr(loadout, "load_session", lambda session_id: saved[-1] if saved else session)
    monkeypatch.setattr(loadout, "save_session", lambda updated, *, compact=False: saved.append(updated) or updated)

    assign_result = loadout.apply_loadout_action("rpg_test", loadout.RpgLoadoutActionRequest(action="assign_hotbar", ability_id="recon_trail_sense", hotbar_slot="7"))
    remove_result = loadout.apply_loadout_action("rpg_test", loadout.RpgLoadoutActionRequest(action="remove_hotbar", hotbar_slot="7"))

    assert assign_result["ok"] is True
    assert saved[0]["state"]["hotbar"]["7"] == "recon_trail_sense"
    assert remove_result["ok"] is True
    assert "7" not in saved[-1]["state"]["hotbar"]


def test_drop_protected_journal_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(loadout, "load_session", lambda session_id: _session())

    result = loadout.apply_loadout_action("rpg_test", loadout.RpgLoadoutActionRequest(action="drop", item_name="Journal"))

    assert result == {"ok": False, "error": "protected_item", "session_id": "rpg_test", "item_name": "Journal"}


def test_salvage_protected_journal_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(loadout, "load_session", lambda session_id: _session())

    result = loadout.apply_loadout_action("rpg_test", loadout.RpgLoadoutActionRequest(action="salvage", item_name="Journal"))

    assert result["ok"] is False
    assert result["error"] == "protected_item_not_salvageable"
    assert result["item_name"] == "Journal"


def test_loadout_action_normalizes_legacy_inventory_and_writes_trace(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    session = _session()
    session["state"]["player"]["inventory"] = ["Rope", {"name": "Iron scrap", "quantity": 2, "material_id": "iron", "item_type": "crafting_material"}]
    monkeypatch.setattr(loadout, "load_session", lambda session_id: session)
    monkeypatch.setattr(loadout, "save_session", lambda updated, *, compact=False: saved.append(updated) or updated)

    result = loadout.apply_loadout_action("rpg_test", loadout.RpgLoadoutActionRequest(action="inspect", item_name="Rope"))

    assert result["ok"] is True
    state = saved[0]["state"]
    inventory = state["player"]["inventory"]
    assert inventory[0]["item_id"] == "rope"
    assert inventory[0]["instance_id"] == "inst_rope_1"
    assert inventory[0]["display"] == {"name": "Rope"}
    assert inventory[1]["item_id"] == "iron"
    trace = state["mechanics"]["inventory_traces"][0]
    assert trace["event"] == "inventory_normalized"
    assert trace["legacy_count"] == 1
    assert trace in state["mechanics"]["item_traces"]
    assert state["mechanics"]["item_loadout_hook_traces"][0]["action"] == "inspect"


def test_session_compat_supports_loadout_action(monkeypatch) -> None:
    monkeypatch.setattr(
        loadout_with_hooks,
        "apply_loadout_action",
        lambda session_id, request, **options: {"ok": True, "session_id": session_id, "action": request.action},
    )

    assert rpg_session_compat.get_rpg_session_payload(
        {"action": "loadout_action", "session_id": "rpg_test", "loadout": {"action": "inspect", "item_name": "Journal"}}
    ) == {"ok": True, "session_id": "rpg_test", "action": "inspect"}
