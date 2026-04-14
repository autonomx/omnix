from app.rpg.economy.menu_catalog import build_provider_transaction_menus


class TestProviderBoundMenus:
    def test_provider_bound_shop_menu_includes_provider(self):
        providers = [{
            "provider_id": "elara",
            "provider_name": "Elara the Merchant",
            "provider_kind": "shop",
            "menu_ids": ["general_store"],
        }]
        out = build_provider_transaction_menus(providers)

        assert out
        menu = out[0]
        assert menu["provider_id"] == "elara"
        assert menu["provider_name"] == "Elara the Merchant"
        assert menu["entries"][0]["action"]["provider_id"] == "elara"

    def test_provider_bound_service_menu_includes_provider(self):
        providers = [{
            "provider_id": "bran",
            "provider_name": "Bran the Innkeeper",
            "provider_kind": "service",
            "menu_ids": ["inn"],
        }]
        out = build_provider_transaction_menus(providers)

        assert out
        menu = out[0]
        assert menu["provider_id"] == "bran"
        assert menu["provider_name"] == "Bran the Innkeeper"
        assert any(entry["action"]["provider_id"] == "bran" for entry in menu["entries"])
