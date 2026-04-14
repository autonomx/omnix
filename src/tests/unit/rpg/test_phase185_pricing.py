from app.rpg.economy.pricing import (
    get_item_price,
    get_service_price,
    resolve_registry_price,
)


class TestPricingRegistry:
    def test_get_item_price_known_item(self):
        assert get_item_price("health_potion") == {"gold": 3}

    def test_get_item_price_alias(self):
        assert get_item_price("potion") == {"gold": 3}

    def test_get_service_price_known_service(self):
        assert get_service_price("inn", "private_room") == {"silver": 2}

    def test_get_service_price_alias(self):
        assert get_service_price("inn", "bed") == {"silver": 8}

    def test_resolve_registry_price_for_buy_action(self):
        action = {
            "action_type": "buy",
            "item_id": "torch",
        }
        assert resolve_registry_price(action) == {"silver": 1}

    def test_resolve_registry_price_for_rent_room(self):
        action = {
            "action_type": "rent_room",
        }
        assert resolve_registry_price(action) == {"silver": 2}

    def test_resolve_registry_price_prefers_explicit_currency_cost(self):
        action = {
            "action_type": "buy",
            "item_id": "torch",
            "currency_cost": {"gold": 9},
        }
        assert resolve_registry_price(action) == {"gold": 9}
