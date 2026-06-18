from app.rpg.session.item_descriptions import (
    ITEM_DESCRIPTION_CONTEXT_VERSION,
    build_item_description_context,
    build_item_mechanics_summary,
    compile_item_description,
)
from app.rpg.session.item_system import build_item_catalog


def _sample_item():
    item = build_item_catalog("classic_fantasy")["iron_dagger"]
    item["description"] = "A serviceable blade."
    return item


def test_item_mechanics_summary_is_compact_and_deterministic():
    summary = build_item_mechanics_summary(_sample_item())

    assert summary["item_id"] == "iron_dagger"
    assert summary["item_type"] == "weapon"
    assert summary["weapon_type"] == "dagger"
    assert summary["rarity"] == "common"
    assert summary["level"] == 1
    assert summary["quantity"] == 1
    assert summary["damage"] == [{"type": "piercing", "amount": 4}]
    assert "starter" in summary["tags"]


def test_description_context_exposes_allowed_and_locked_fields():
    context = build_item_description_context(_sample_item(), genre="cyberpunk")

    assert context["version"] == ITEM_DESCRIPTION_CONTEXT_VERSION
    assert context["item_id"] == "iron_dagger"
    assert context["suggested_name"] == "Streetline mono-knife"
    assert "name" in context["allowed_display_fields"]
    assert "visual_prompt" in context["allowed_display_fields"]
    assert "damage" in context["locked_mechanic_fields"]
    assert "effects" in context["locked_mechanic_fields"]
    assert context["mechanics_summary"]["damage"] == [{"type": "piercing", "amount": 4}]


def test_compile_item_description_ignores_engine_owned_fields():
    item = _sample_item()
    result = compile_item_description(
        item,
        {
            "name": "Moonlit Letter Opener",
            "description": "A refined description.",
            "damage": [{"type": "fire", "amount": 999}],
            "value": 9999,
            "unknown_field": "ignore me",
        },
        genre="detective_noir",
    )

    assert result["ok"] is True
    assert result["item"]["name"] == "Moonlit Letter Opener"
    assert result["item"]["description"] == "A refined description."
    assert result["item"]["damage"] == item["damage"]
    assert result["item"]["value"] == item["value"]
    assert "damage" in result["ignored_fields"]
    assert "value" in result["ignored_fields"]
    assert "unknown_field" in result["ignored_fields"]
    assert result["trace"]["mechanics_preserved"] is True
    assert result["trace"]["event"] == "item_description_compiled"


def test_compile_item_description_fills_genre_name_when_blank():
    item = _sample_item()
    item.pop("name", None)

    result = compile_item_description(item, {}, genre="cyberpunk")

    assert result["ok"] is True
    assert result["item"]["name"] == "Streetline mono-knife"
    assert "filled_genre_name" in result["repairs"]
    assert result["context"]["current_display"]["name"] == "Streetline mono-knife"
