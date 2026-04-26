from app.rpg.session.ambient_intent import (
    is_ambient_wait_or_listen_intent,
    is_room_context_ambient_not_lodging,
)


def test_wait_and_listen_to_room_is_ambient_not_lodging():
    assert is_ambient_wait_or_listen_intent("I wait and listen to the room")
    assert is_room_context_ambient_not_lodging("I wait and listen to the room")


def test_rent_room_is_not_ambient():
    assert not is_ambient_wait_or_listen_intent("I ask Bran for a room to rent")
    assert not is_room_context_ambient_not_lodging("I ask Bran for a room to rent")


def test_buy_meal_is_not_ambient():
    assert not is_ambient_wait_or_listen_intent("I buy a meal from Bran")