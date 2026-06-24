from __future__ import annotations

from app.rpg.session.combat_event_cards import (
    COMBAT_EVENT_CARD_VERSION,
    attach_combat_event_cards,
    build_combat_event_cards,
    card_from_combat_event,
)


def test_card_from_movement_event() -> None:
    card = card_from_combat_event({"type": "move", "actor": "Shambler 1", "to": [7, 6], "distance": "32 feet"})

    assert card["format_version"] == COMBAT_EVENT_CARD_VERSION
    assert card["card_type"] == "movement"
    assert card["title"] == "Shambler 1 moves"
    assert "(7, 6)" in card["detail"]


def test_card_from_save_event() -> None:
    card = card_from_combat_event(
        {"type": "save", "actor": "Shambler", "target": "Deacon", "save": "Wisdom", "dc": 10, "roll": 4, "result": "failure"}
    )

    assert card["card_type"] == "saving_throw"
    assert card["target"] == "Deacon"
    assert card["result"] == "failure"
    assert "DC 10" in card["detail"]


def test_build_combat_event_cards_from_nested_payload() -> None:
    cards = build_combat_event_cards(
        {
            "result": {
                "combat_delta": {
                    "events": [
                        {"type": "ability", "actor": "Shambler", "name": "Guttural Moan"},
                        {"type": "condition", "actor": "Shambler", "target": "Deacon", "condition": "Frightened"},
                    ]
                }
            }
        }
    )

    assert [card["card_type"] for card in cards] == ["ability", "condition"]


def test_attach_combat_event_cards_copies_to_nested_result() -> None:
    result = {"ok": True, "result": {"events": [{"type": "attack", "actor": "Ryder", "target": "Shambler", "damage": 6}]}}

    attached = attach_combat_event_cards(result)

    assert attached["combat_event_cards"][0]["card_type"] == "attack"
    assert attached["result"]["combat_event_cards"][0]["target"] == "Shambler"
