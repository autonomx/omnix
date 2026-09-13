from __future__ import annotations

from app.rpg.session.item_rewards import generate_item_rewards, merge_reward_items, reward_table


def test_generate_item_rewards_is_deterministic_for_same_seed() -> None:
    first = generate_item_rewards("road_cache", seed="seed-1")
    second = generate_item_rewards("road_cache", seed="seed-1")

    assert first["ok"] is True
    assert first["outputs"] == second["outputs"]
    assert first["trace"] == second["trace"]


def test_reward_sources_have_distinct_table_identities() -> None:
    road = generate_item_rewards("road_cache", seed="seed-2")
    forest = generate_item_rewards("forest_cache", seed="seed-2")

    assert road["source_id"] == "road_cache"
    assert forest["source_id"] == "forest_cache"
    assert road["trace"]["source_name"] == "Road Cache"
    assert forest["trace"]["source_name"] == "Forest Cache"


def test_ruin_cache_can_generate_documents_or_artifacts() -> None:
    result = generate_item_rewards("ruin_cache", seed="ruin-seed-4")

    assert result["ok"] is True
    item_types = {item.get("item_type") for item in result["outputs"]}
    assert item_types & {"document", "artifact", "crafting_material"}
    assert result["trace"]["source_id"] == "ruin_cache"
    assert result["trace"]["mechanics_source"] == "engine_item_reward_table_v1"


def test_unknown_reward_source_uses_generic_cache() -> None:
    table = reward_table("unknown_cache")
    result = generate_item_rewards("unknown_cache", seed="fallback")

    assert table["source_id"] == "generic_cache"
    assert result["source_id"] == "generic_cache"
    assert result["outputs"]


def test_merge_reward_items_stacks_matching_stackables() -> None:
    merged = merge_reward_items(
        [
            {"item_id": "copper_coin", "name": "Copper coins", "quantity": 2, "stackable": True, "rarity": "common"},
            {"item_id": "copper_coin", "name": "Copper coins", "quantity": 3, "stackable": True, "rarity": "common"},
            {"item_id": "rune_note", "name": "Rune note", "quantity": 1, "stackable": False, "rarity": "uncommon"},
            {"item_id": "rune_note", "name": "Rune note", "quantity": 1, "stackable": False, "rarity": "uncommon"},
        ]
    )

    assert merged[0]["quantity"] == 5
    assert [item["item_id"] for item in merged].count("rune_note") == 2


def test_reward_trace_summarizes_outputs_without_mutating_mechanics() -> None:
    result = generate_item_rewards("forest_cache", seed="trace-seed", context={"biome": "evergreen"})

    assert result["ok"] is True
    trace = result["trace"]
    assert trace["event"] == "item_rewards_generated"
    assert trace["roll_count"] == 2
    assert trace["outputs"] == [
        {
            "item_id": item.get("item_id"),
            "name": item.get("name"),
            "quantity": item.get("quantity"),
            "rarity": item.get("rarity"),
            "item_type": item.get("item_type"),
            "material_id": item.get("material_id", ""),
        }
        for item in result["outputs"]
    ]
