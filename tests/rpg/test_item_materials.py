from __future__ import annotations

from app.rpg.session.item_materials import (
    apply_material_fiction_proposal,
    build_salvage_outputs,
    material_stack,
    salvage_item,
    validate_material_stack,
)


def test_material_stack_keeps_canonical_identity_for_display_fiction() -> None:
    material = material_stack("iron", 3, theme_tags=["moonlit"])
    result = apply_material_fiction_proposal(
        material,
        {
            "display_name": "Moon-Touched Iron Fragments",
            "description": "Silver-veined scraps recovered from a lunar blade.",
            "material_id": "starblood",
            "quantity": 999,
            "rarity": "mythic",
        },
    )

    assert result.ok is True
    assert result.material["material_id"] == "iron"
    assert result.material["material_role"] == "metal"
    assert result.material["quantity"] == 3
    assert result.material["display"]["name"] == "Moon-Touched Iron Fragments"
    assert result.material["display"]["description"] == "Silver-veined scraps recovered from a lunar blade."
    assert set(result.ignored_fields) >= {"material_id", "quantity", "rarity"}


def test_unknown_material_identity_is_rejected_in_validation() -> None:
    strange = {
        "material_id": "starblood_resin",
        "material_role": "arcane_reagent",
        "quantity": 1,
    }

    validation = validate_material_stack(strange)

    assert validation.ok is False
    assert validation.error == "unsupported_material_id"


def test_salvage_uses_explicit_material_profile_and_ai_display_names() -> None:
    item = {
        "id": "moonlit_ashblade",
        "name": "Moonlit Ashblade",
        "item_type": "weapon",
        "weapon_type": "sword",
        "rarity": "rare",
        "theme_tags": ["moonlit"],
        "salvage_outputs": [
            {"material_id": "iron", "quantity": 8},
            {"material_id": "moon_essence", "quantity": 2},
        ],
    }

    result = salvage_item(
        item,
        fiction_proposals={
            "iron": {"display_name": "Moon-Touched Iron Fragments"},
            "moon_essence": {"display_name": "Crystallized Lunar Essence"},
        },
    )

    assert result.ok is True
    by_id = {output["material_id"]: output for output in result.outputs}
    assert by_id["iron"]["quantity"] == 8
    assert by_id["iron"]["display"]["name"] == "Moon-Touched Iron Fragments"
    assert by_id["moon_essence"]["material_role"] == "arcane_reagent"
    assert by_id["moon_essence"]["display"]["name"] == "Crystallized Lunar Essence"
    assert result.trace["event"] == "item_salvaged"
    assert result.trace["outputs"][0]["material_id"] == "iron"


def test_salvage_derives_outputs_from_item_type_and_tags() -> None:
    weapon_outputs = build_salvage_outputs({"id": "rusted_spear", "name": "Rusted spear", "item_type": "weapon", "weapon_type": "spear"})
    chair_outputs = build_salvage_outputs({"id": "broken_chair", "name": "Broken chair", "item_type": "world_object", "tags": ["wood", "chair", "salvageable"]})
    bottle_outputs = build_salvage_outputs({"id": "empty_bottle", "name": "Empty bottle", "item_type": "junk", "tags": ["glass", "bottle"]})

    assert {output["material_id"]: output["quantity"] for output in weapon_outputs} == {"iron": 3, "leather": 1}
    assert chair_outputs == [material_stack("wood", 2)]
    assert bottle_outputs == [material_stack("glass", 1)]


def test_protected_items_cannot_be_salvaged() -> None:
    result = salvage_item({"id": "journal", "name": "Journal", "item_type": "quest", "tags": ["protected"]})

    assert result.ok is False
    assert result.error == "protected_item_not_salvageable"
    assert result.outputs == []


def test_salvage_fallback_names_are_genre_aware_without_changing_materials() -> None:
    cyberpunk_result = salvage_item(
        {"id": "street_pistol", "name": "Street Pistol", "item_type": "weapon", "weapon_type": "firearm", "tags": ["metal", "tech"]},
        genre="cyberpunk",
    )
    fantasy_result = salvage_item(
        {"id": "iron_dagger", "name": "Iron Dagger", "item_type": "weapon", "weapon_type": "dagger"},
        genre="classic_fantasy",
    )

    assert cyberpunk_result.ok is True
    assert fantasy_result.ok is True
    assert cyberpunk_result.outputs[0]["material_id"] == "iron"
    assert fantasy_result.outputs[0]["material_id"] == "iron"
    assert cyberpunk_result.outputs[0]["display"]["name"] == "Ferrocarbon Alloy Shards"
    assert fantasy_result.outputs[0]["display"]["name"] == "Iron scrap"
