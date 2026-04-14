from app.rpg.economy.action_generator import build_menu_action


class TestActionGenerator:
    def test_build_menu_action_buy(self):
        out = build_menu_action({
            "action_type": "buy",
            "item_id": "torch",
            "quantity": 1,
        })
        assert out["action_type"] == "buy"
        assert out["item_id"] == "torch"
        assert out["apply_cost"] is True
        assert "currency_cost" in out

    def test_build_menu_action_service(self):
        out = build_menu_action({
            "action_type": "rent_room",
            "service_type": "inn",
            "service_id": "private_room",
        })
        assert out["action_type"] == "rent_room"
        assert out["service_type"] == "inn"
        assert out["service_id"] == "private_room"
        assert out["apply_cost"] is True
        assert "currency_cost" in out
