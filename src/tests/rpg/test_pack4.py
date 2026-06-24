from app.rpg.p31_pack import pack


def test_pack4():
    assert pack("a", "b", "c", "d") == ("a", "b", "c", "d")
