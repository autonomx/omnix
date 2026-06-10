from app.rpg.session import runtime_part24, runtime_part25, runtime_part26


def test_phase13_49_runtime_part26_base_binding_does_not_self_recurse(monkeypatch):
    calls = []

    def fake_base(session_id, player_input, action=None, *, performance_override=None):
        calls.append((session_id, player_input, action, performance_override))
        return {"result": {}, "resolved_result": {}, "narration_context": {}}

    # Simulate the observed failure mode where the module global alias is polluted
    # back to the wrapper itself after import. The wrapper must still use the
    # definition-time base function binding rather than this mutable global.
    monkeypatch.setattr(runtime_part26, "_base_apply_turn_authoritative", runtime_part26._apply_turn_authoritative)
    monkeypatch.setattr(runtime_part26, "_COMBAT_QUEST_BASE_APPLY_TURN_AUTHORITATIVE", runtime_part26._apply_turn_authoritative)

    payload = runtime_part26._apply_turn_authoritative(
        "session-1",
        "I'm looking for a quest.",
        {"kind": "dialogue"},
        performance_override={"probe": True},
        _base_authoritative=fake_base,
    )

    assert calls == [("session-1", "I'm looking for a quest.", {"kind": "dialogue"}, {"probe": True})]
    assert payload["result"] == {}
    assert payload["resolved_result"] == {}
    assert payload["narration_context"] == {}


def test_phase13_49_combat_runtime_default_base_bindings_are_not_self_references():
    for module in (runtime_part24, runtime_part25, runtime_part26):
        defaults = module._apply_turn_authoritative.__kwdefaults__ or {}
        bound_base = defaults.get("_base_authoritative")

        assert bound_base is not None
        assert bound_base is not module._apply_turn_authoritative


def test_phase13_49_runtime_part25_ignores_polluted_base_alias(monkeypatch):
    calls = []

    def fake_base(session_id, player_input, action=None, *, performance_override=None):
        calls.append((session_id, player_input, action, performance_override))
        return {"result": {}, "resolved_result": {}, "narration_context": {}}

    monkeypatch.setattr(runtime_part25, "_base_apply_turn_authoritative", runtime_part26._apply_turn_authoritative)
    monkeypatch.setattr(runtime_part25, "_COMBAT_QUEST_SYNC_BASE_APPLY_TURN_AUTHORITATIVE", runtime_part26._apply_turn_authoritative)

    payload = runtime_part25._apply_turn_authoritative(
        "session-2",
        "What do you say, Bran?",
        {"kind": "dialogue"},
        performance_override={"probe": True},
        _base_authoritative=fake_base,
    )

    assert calls == [("session-2", "What do you say, Bran?", {"kind": "dialogue"}, {"probe": True})]
    assert payload["result"] == {}
    assert payload["resolved_result"] == {}
    assert payload["narration_context"] == {}
