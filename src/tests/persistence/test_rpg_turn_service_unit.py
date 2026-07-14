from app.persistence.rpg_turn_service import _campaign_record_id


def test_campaign_record_ids_do_not_collide_at_same_revision() -> None:
    first = _campaign_record_id("turn", "rpg:first", 1)
    second = _campaign_record_id("turn", "rpg:second", 1)

    assert first == "turn:rpg:first:1"
    assert second == "turn:rpg:second:1"
    assert first != second
