from app.rpg.session.item_fiction_pipeline import (
    build_item_fiction_prompt_packet,
    apply_item_fiction_pipeline_response,
)
from app.rpg.session.item_system import build_item_catalog


def test_prompt_packet_exposes_safe_display_boundary() -> None:
    item = build_item_catalog()["iron_dagger"]

    packet = build_item_fiction_prompt_packet(item, genre="classic_fantasy", tone="weathered")

    assert packet["version"] == "item_fiction_pipeline_v1"
    assert packet["item_id"] == "iron_dagger"
    assert "name" in packet["allowed_display_fields"]
    assert "damage" in packet["locked_mechanic_fields"]
    assert "Do not change mechanics" in packet["prompt"]
    assert packet["context"]["mechanics_summary"]["damage"][0]["amount"] == item["damage"][0]["amount"]


def test_pipeline_applies_nested_display_response() -> None:
    item = build_item_catalog()["torch"]
    response = {
        "item": {
            "name": "Soot-black travel torch",
            "description": "A compact light source wrapped in waxed cloth.",
            "flavor_tags": ["travel", "smoke"],
            "icon": "🔥",
        }
    }

    result = apply_item_fiction_pipeline_response(item, response)

    assert result["ok"] is True
    assert result["item"]["name"] == "Soot-black travel torch"
    assert result["item"]["description"] == "A compact light source wrapped in waxed cloth."
    assert result["trace"]["mechanics_preserved"] is True
    assert result["trace"]["accepted_fields"] == ["description", "flavor_tags", "icon", "name"]


def test_pipeline_ignores_mechanics_from_response() -> None:
    item = build_item_catalog()["simple_bow"]
    original_damage = item["damage"]
    response = {
        "name": "Ashwood trail bow",
        "damage": [{"type": "plasma", "amount": 999}],
        "value": 9999,
        "quantity": 99,
    }

    result = apply_item_fiction_pipeline_response(item, response, genre="classic_fantasy")

    assert result["ok"] is True
    assert result["item"]["name"] == "Ashwood trail bow"
    assert result["item"]["damage"] == original_damage
    assert result["item"]["value"] == item["value"]
    assert result["item"]["quantity"] == item["quantity"]
    assert set(result["ignored_fields"]) >= {"damage", "quantity", "value"}
    assert result["trace"]["mechanics_preserved"] is True


def test_pipeline_handles_empty_response() -> None:
    item = build_item_catalog()["ration"]

    result = apply_item_fiction_pipeline_response(item, None)

    assert result["ok"] is True
    assert result["item"]["item_id"] == "ration"
    assert result["proposal"] == {}
    assert result["trace"]["accepted_fields"] == []
