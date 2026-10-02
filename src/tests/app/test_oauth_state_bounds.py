from app.assistant_tools import connections


def test_pending_oauth_state_is_capacity_ttl_bounded_and_clearable(monkeypatch) -> None:
    connections.clear_pending_oauth_states()
    monkeypatch.setattr(connections, "_MAX_PENDING_OAUTH_STATES", 2)
    monkeypatch.setattr(connections, "_OAUTH_STATE_TTL_SECONDS", 5.0)
    now = {"value": 10.0}
    monkeypatch.setattr(connections.time, "monotonic", lambda: now["value"])

    first = connections._issue_oauth_state("google", "gmail")
    connections._issue_oauth_state("google", "calendar")
    third = connections._issue_oauth_state("github", "github")
    assert first not in connections._PENDING_OAUTH_STATES
    assert third in connections._PENDING_OAUTH_STATES

    now["value"] = 16.0
    current = connections._issue_oauth_state("google", "contacts")
    assert connections._PENDING_OAUTH_STATES == {
        current: ("google", "contacts", 21.0),
    }
    connections.clear_pending_oauth_states()
    assert connections._PENDING_OAUTH_STATES == {}
