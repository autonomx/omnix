from app.rpg.session.item_content_packs import build_item_content_bundle, build_item_content_pack


def test_starter_survival_pack_contains_normalized_items() -> None:
    pack = build_item_content_pack("starter_survival")

    assert pack["pack_id"] == "starter_survival"
    assert pack["recipes"] == {}
    assert pack["merchant_profiles"] == {}
    assert pack["items"]["bandage_roll"]["item_id"] == "bandage_roll"
    assert pack["items"]["bandage_roll"]["stackable"] is True
    assert pack["items"]["campfire_kit"]["effects"][0]["status"] == "campfire_lit"


def test_field_crafting_pack_adds_recipes_without_merchants() -> None:
    pack = build_item_content_pack("field_crafting")

    assert set(pack["recipes"]) == {"recipe_bandage_roll", "recipe_campfire_kit", "recipe_trail_marker_chalk"}
    assert pack["recipes"]["recipe_bandage_roll"]["ingredients"] == [
        {"item_id": "leather_strip", "quantity": 1},
        {"item_id": "keenleaf", "quantity": 1},
    ]
    assert pack["recipes"]["recipe_trail_marker_chalk"]["output_quantity"] == 2
    assert pack["merchant_profiles"] == {}


def test_merchant_basics_pack_adds_supplier_profile() -> None:
    pack = build_item_content_pack("merchant_basics")
    profile = pack["merchant_profiles"]["roadside_supplier"]

    assert profile["name"] == "Roadside supplier"
    assert "bandage_roll" in profile["stock_item_ids"]
    assert profile["buy_markup"] > 1
    assert 0 < profile["sell_markdown"] < 1


def test_content_bundle_merges_items_recipes_and_merchants() -> None:
    bundle = build_item_content_bundle()

    assert bundle["pack_ids"] == ["starter_survival", "field_crafting", "merchant_basics"]
    assert "bandage_roll" in bundle["items"]
    assert "recipe_campfire_kit" in bundle["recipes"]
    assert "roadside_supplier" in bundle["merchant_profiles"]
    assert bundle["warnings"] == []


def test_unknown_pack_is_non_fatal() -> None:
    bundle = build_item_content_bundle(["starter_survival", "unknown"])

    assert "bandage_roll" in bundle["items"]
    assert bundle["warnings"] == ["unknown_content_pack"]
