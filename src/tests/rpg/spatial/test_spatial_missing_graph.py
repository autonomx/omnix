from app.rpg.spatial.audibility import can_hear_entity
from app.rpg.spatial.movement import can_move_between
from app.rpg.spatial.visibility import can_see_entity


def test_can_see_entity_empty_graph_is_not_same_area():
    result = can_see_entity({}, "player", "bran")

    assert result["ok"] is False
    assert result["reason"] in {"unknown_entity", "unknown_area"}


def test_can_hear_entity_empty_graph_is_not_same_area():
    result = can_hear_entity({}, "player", "bran")

    assert result["ok"] is False
    assert result["reason"] in {"unknown_entity", "unknown_area"}


def test_can_move_between_empty_area_fails_unknown_area():
    result = can_move_between({}, "", "private_room")

    assert result["ok"] is False
    assert result["reason"] == "unknown_area"