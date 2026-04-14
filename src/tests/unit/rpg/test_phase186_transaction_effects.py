from app.rpg.economy.transaction_effects import (
    apply_item_purchase_effect,
    apply_service_purchase_effect,
    apply_transaction_effects,
    ensure_player_status_state,
)


class TestPlayerStatusState:
    def test_ensure_player_status_state_defaults(self):
        out = ensure_player_status_state({})
        assert out["resources"]["fatigue"] == 0
        assert out["resources"]["hunger"] == 0
        assert out["statuses"] == []
        assert out["service_flags"] == {}
        assert out["lodging"] == ""


class TestItemPurchaseEffects:
    def test_item_purchase_adds_inventory_item(self):
        simulation_state = {
            "player_state": {
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 0, "silver": 0, "copper": 0},
                    "last_loot": [],
                }
            }
        }
        action = {
            "item_id": "torch",
            "quantity": 2,
            "item_name": "Torch",
        }

        out = apply_item_purchase_effect(simulation_state, action)
        inventory_state = out["simulation_state"]["player_state"]["inventory_state"]

        assert any(item["item_id"] == "torch" and item["qty"] == 2 for item in inventory_state["items"])
        assert out["effect_result"]["items_added"][0]["item_id"] == "torch"


class TestServicePurchaseEffects:
    def test_private_room_applies_lodging_and_status(self):
        simulation_state = {
            "player_state": {
                "resources": {"fatigue": 6, "hunger": 1, "thirst": 0},
                "statuses": [],
                "service_flags": {},
                "lodging": "",
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 0, "silver": 0, "copper": 0},
                    "last_loot": [],
                },
            }
        }
        action = {
            "action_type": "rent_room",
        }

        out = apply_service_purchase_effect(simulation_state, action)
        player_state = out["simulation_state"]["player_state"]

        assert player_state["lodging"] == "private_room"
        assert "rested" in player_state["statuses"]
        assert "well_rested" in player_state["statuses"]
        assert player_state["resources"]["fatigue"] == 2

    def test_meal_reduces_hunger_and_adds_fed_status(self):
        simulation_state = {
            "player_state": {
                "resources": {"fatigue": 0, "hunger": 5, "thirst": 0},
                "statuses": [],
                "service_flags": {},
                "lodging": "",
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 0, "silver": 0, "copper": 0},
                    "last_loot": [],
                },
            }
        }
        action = {
            "action_type": "use_service",
            "service_type": "inn",
            "service_id": "meal",
        }

        out = apply_service_purchase_effect(simulation_state, action)
        player_state = out["simulation_state"]["player_state"]

        assert player_state["resources"]["hunger"] == 2
        assert "fed" in player_state["statuses"]

    def test_travel_sets_flag(self):
        simulation_state = {
            "player_state": {
                "resources": {"fatigue": 0, "hunger": 0, "thirst": 0},
                "statuses": [],
                "service_flags": {},
                "lodging": "",
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 0, "silver": 0, "copper": 0},
                    "last_loot": [],
                },
            }
        }
        action = {
            "action_type": "use_service",
            "service_type": "travel",
            "service_id": "local_passage",
        }

        out = apply_service_purchase_effect(simulation_state, action)
        player_state = out["simulation_state"]["player_state"]

        assert player_state["service_flags"]["local_passage_used"] is True

    def test_repair_service_repairs_item(self):
        simulation_state = {
            "player_state": {
                "resources": {"fatigue": 0, "hunger": 0, "thirst": 0},
                "statuses": [],
                "service_flags": {},
                "lodging": "",
                "inventory_state": {
                    "items": [{
                        "item_id": "iron_sword",
                        "qty": 1,
                        "name": "Iron Sword",
                        "durability": {"current": 2, "max": 5},
                    }],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 0, "silver": 0, "copper": 0},
                    "last_loot": [],
                },
            }
        }
        action = {
            "action_type": "use_service",
            "service_type": "repair",
            "service_id": "weapon_repair",
            "repair_item_id": "iron_sword",
        }

        out = apply_service_purchase_effect(simulation_state, action)
        inventory_state = out["simulation_state"]["player_state"]["inventory_state"]
        repaired_item = inventory_state["items"][0]

        assert repaired_item["durability"]["current"] == 4
        assert out["effect_result"]["service_effects"]["repair"]["applied"] is True


class TestTransactionDispatcher:
    def test_dispatch_item_purchase(self):
        simulation_state = {
            "player_state": {
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 0, "silver": 0, "copper": 0},
                    "last_loot": [],
                }
            }
        }
        action = {"item_id": "torch"}
        action_metadata = {"transaction_kind": "item_purchase"}

        out = apply_transaction_effects(simulation_state, action, action_metadata)
        assert out["effect_result"]["items_added"][0]["item_id"] == "torch"

    def test_dispatch_service_purchase(self):
        simulation_state = {
            "player_state": {
                "resources": {"fatigue": 4, "hunger": 0, "thirst": 0},
                "statuses": [],
                "service_flags": {},
                "lodging": "",
                "inventory_state": {
                    "items": [],
                    "equipment": {},
                    "capacity": 50,
                    "currency": {"gold": 0, "silver": 0, "copper": 0},
                    "last_loot": [],
                },
            }
        }
        action = {"action_type": "rent_room"}
        action_metadata = {"transaction_kind": "service_purchase"}

        out = apply_transaction_effects(simulation_state, action, action_metadata)
        assert out["simulation_state"]["player_state"]["lodging"] == "private_room"
