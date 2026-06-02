from copy import deepcopy


def test_ci_phase2_economy_inventory_survives_session_package_roundtrip():
    from app.rpg.economy.inn_services import rent_room_and_rest
    from app.rpg.economy.merchant_transactions import buy_from_merchant, sell_to_merchant
    from app.rpg.economy.persistence_snapshot import build_phase2_persistence_snapshot
    from app.rpg.economy.survival import apply_survival_pressure, consume_food, consume_water
    from app.rpg.session.service import export_session_as_package, import_session_from_package

    state = {
        "player_state": {
            "hp": 4,
            "max_hp": 12,
            "fatigue": 3,
            "inventory_state": {
                "items": [
                    {"item_id": "combat_knife", "qty": 1},
                    {"item_id": "ration", "qty": 2},
                    {"item_id": "water_skin", "qty": 2},
                ],
                "currency": {"gold": 0, "silver": 30, "copper": 0},
            },
            "survival_state": {"hunger": 70, "thirst": 75, "last_pressure_tick": 0},
        }
    }

    buy_from_merchant(state, item_id="healing_potion", qty=1, tick=1)
    sell_to_merchant(state, item_id="combat_knife", qty=1, tick=2)
    rent_room_and_rest(state, tick=3)
    consume_food(state, tick=4)
    consume_water(state, tick=5)
    apply_survival_pressure(state, tick=13)

    before_snapshot = build_phase2_persistence_snapshot(state)
    session = {
        "manifest": {
            "id": "session:phase2:persistence",
            "session_id": "session:phase2:persistence",
            "schema_version": 4,
            "title": "Phase 2 persistence gate",
        },
        "simulation_state": deepcopy(state),
        "runtime_state": {},
        "installed_packs": ["base"],
    }

    package_payload = export_session_as_package(session)
    import_result = import_session_from_package(package_payload)
    after_snapshot = build_phase2_persistence_snapshot(import_result["session"]["simulation_state"])

    assert import_result["ok"] is True
    assert after_snapshot == before_snapshot
    assert after_snapshot["source"] == "deterministic_phase2_persistence_snapshot"
    assert after_snapshot["player_inventory"]["items"] == {
        "healing_potion": 1,
        "ration": 1,
        "water_skin": 1,
    }
    assert after_snapshot["player_inventory"]["currency"] == {"gold": 0, "silver": 20, "copper": 0}
    assert after_snapshot["player_rest_state"]["rested"] is True
    assert len(after_snapshot["economy_state"]["service_transaction_log"]) == 1
    assert len(after_snapshot["economy_state"]["survival_log"]) == 3

    merchant = after_snapshot["economy_state"]["merchants"]["merchant:elara"]
    assert len(merchant["transaction_log"]) == 2
    assert merchant["stock"]["healing_potion"] == 2
    assert merchant["stock"]["combat_knife"] == 3


def test_ci_phase2_persistence_snapshot_normalizes_item_order_and_currency_shape():
    from app.rpg.economy.persistence_snapshot import build_phase2_persistence_snapshot

    state = {
        "player_state": {
            "inventory_state": {
                "items": [
                    {"item_id": "water_skin", "qty": 1},
                    {"item_id": "ration", "qty": 1},
                    {"item_id": "water_skin", "qty": 2},
                ],
                "currency": {"silver": 2},
            }
        }
    }

    snapshot = build_phase2_persistence_snapshot(state)

    assert snapshot["player_inventory"]["items"] == {"ration": 1, "water_skin": 3}
    assert snapshot["player_inventory"]["currency"] == {"gold": 0, "silver": 2, "copper": 0}
    assert snapshot["economy_state"]["merchants"] == {}
    assert snapshot["source"] == "deterministic_phase2_persistence_snapshot"
