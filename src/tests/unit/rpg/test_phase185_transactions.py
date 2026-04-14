from app.rpg.economy.transactions import (
    build_transaction_metadata,
    enrich_action_with_registry_price,
)


class TestTransactionEnrichment:
    def test_enrich_buy_action_with_registry_price(self):
        action = {
            "action_type": "buy",
            "item_id": "torch",
        }
        out = enrich_action_with_registry_price(action)

        assert out["currency_cost"] == {"gold": 0, "silver": 1, "copper": 0}

    def test_enrich_rent_room_action_with_registry_price(self):
        action = {
            "action_type": "rent_room",
        }
        out = enrich_action_with_registry_price(action)

        assert out["currency_cost"] == {"gold": 0, "silver": 2, "copper": 0}

    def test_explicit_price_not_overridden(self):
        action = {
            "action_type": "buy",
            "item_id": "torch",
            "currency_cost": {"gold": 9},
        }
        out = enrich_action_with_registry_price(action)

        assert out["currency_cost"] == {"gold": 9}

    def test_build_transaction_metadata_for_item_purchase(self):
        action = {
            "action_type": "buy",
            "item_id": "torch",
            "currency_cost": {"silver": 1},
        }
        out = build_transaction_metadata(action)

        assert out["transaction_kind"] == "item_purchase"
        assert out["price_source"] == "registry_or_authoritative"

    def test_build_transaction_metadata_for_service_purchase(self):
        action = {
            "action_type": "rent_room",
            "currency_cost": {"silver": 2},
        }
        out = build_transaction_metadata(action)

        assert out["transaction_kind"] == "service_purchase"
        assert out["price_source"] == "registry_or_authoritative"
