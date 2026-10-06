from app.config import env


def test_environment_read_name_diagnostics_have_capacity_ttl_and_clear(monkeypatch) -> None:
    env.clear_read_names()
    monkeypatch.setattr(env, "_MAX_READ_NAMES", 2)
    monkeypatch.setattr(env, "_READ_NAME_TTL_SECONDS", 5.0)
    now = {"value": 10.0}
    monkeypatch.setattr(env.time, "monotonic", lambda: now["value"])

    env._record("FIRST")
    env._record("SECOND")
    env._record("THIRD")
    assert env.read_names() == ("SECOND", "THIRD")

    now["value"] = 16.0
    assert env.read_names() == ()
    env._record("FOURTH")
    env.clear_read_names()
    assert env.read_names() == ()
