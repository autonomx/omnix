from app.rpg.economy.menu_catalog import (
    build_available_transaction_menus,
    build_service_menu,
    build_shop_menu,
)


class TestMenuCatalog:
    def test_build_shop_menu_general_store(self):
        out = build_shop_menu("general_store")
        assert out["menu_type"] == "shop"
        assert out["entries"]
        assert out["entries"][0]["action"]["action_type"] == "buy"

    def test_build_service_menu_inn(self):
        out = build_service_menu("inn")
        assert out["menu_type"] == "service"
        assert any(entry["action"]["action_type"] in {"rent_room", "rent_bed", "use_service"} for entry in out["entries"])

    def test_build_available_transaction_menus_from_tags(self):
        out = build_available_transaction_menus(["inn", "general_store"])
        menu_ids = {menu["menu_id"] for menu in out}
        assert "inn" in menu_ids
        assert "general_store" in menu_ids
