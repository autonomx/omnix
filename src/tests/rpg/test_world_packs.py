from __future__ import annotations

from app.rpg.world_packs import (
    LoreEntry,
    ModOverlay,
    WorldPack,
    validate_lore_entry,
    validate_overlay,
    validate_world_pack,
    visible_lore_for_scope,
    world_pack_report,
)


def _pack() -> WorldPack:
    return WorldPack(
        "vance",
        "New Vance",
        regions=("city",),
        lore=(LoreEntry("fog", "Fog", "The city is hazy.", "world", priority=5),),
    )


def test_world_pack_validates_required_fields() -> None:
    assert validate_world_pack(_pack()) == ()
    assert "missing_regions" in validate_world_pack(WorldPack("empty", "Empty"))


def test_lore_entry_validation_and_visibility_sorting() -> None:
    assert validate_lore_entry(LoreEntry("", "Title", "Body", "world")) == ("missing_lore_key",)
    pack = WorldPack(
        "pack",
        "Pack",
        regions=("r",),
        lore=(LoreEntry("b", "B", "Body", "world", priority=1), LoreEntry("a", "A", "Body", "world", priority=5)),
    )

    assert [entry.key for entry in visible_lore_for_scope(pack, "world")] == ["a", "b"]


def test_overlay_validation_blocks_state_mutation_keys() -> None:
    overlay = ModOverlay("bad", "item", {"currency": 50})

    assert validate_overlay(overlay) == ("forbidden_overlay_key:currency",)


def test_world_pack_with_overlay_is_pure() -> None:
    pack = _pack()
    updated = pack.with_overlay(ModOverlay("style", "prompt_style", {"tone": "gritty"}))

    assert pack.overlays == ()
    assert updated.overlays[0].overlay_id == "style"


def test_world_pack_report_includes_validation() -> None:
    payload = world_pack_report(_pack())

    assert payload["pack"]["pack_id"] == "vance"
    assert payload["validation_issues"] == []
