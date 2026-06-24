from app.rpg.env_track3 import make


def test_make_tuple():
    assert make("a", "b", "c") == ("a", "b", "c")
