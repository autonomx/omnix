from app.rpg.economy.provider_catalog import (
    derive_npc_transaction_providers,
    derive_world_transaction_providers,
)


class TestProviderCatalog:
    def test_innkeeper_exposes_inn_menu(self):
        npcs = [{
            "npc_id": "bran",
            "name": "Bran the Innkeeper",
            "role": "innkeeper",
        }]
        out = derive_npc_transaction_providers(npcs)

        assert out
        assert out[0]["provider_id"] == "bran"
        assert "inn" in out[0]["menu_ids"]

    def test_merchant_exposes_general_store(self):
        npcs = [{
            "npc_id": "elara",
            "name": "Elara the Merchant",
            "profession": "merchant",
        }]
        out = derive_npc_transaction_providers(npcs)

        assert out
        assert "general_store" in out[0]["menu_ids"]

    def test_world_entity_can_expose_repair(self):
        entities = [{
            "entity_id": "forge_01",
            "name": "Town Forge",
            "entity_type": "repair_shop",
        }]
        out = derive_world_transaction_providers(entities)

        assert out
        assert "repair" in out[0]["menu_ids"]
