def test_runtime_facade_uses_static_exports_from_responsibility_modules():
    from app.rpg.session import (
        runtime,
        session_runtime_store,
        turn_response_composition,
    )

    assert runtime.load_runtime_session is session_runtime_store.load_runtime_session
    assert runtime.apply_turn is turn_response_composition.apply_turn
    assert "_apply_turn_authoritative" not in vars(runtime)
    assert not hasattr(runtime, "__getattr__")
    assert runtime.get_runtime_wrapper_drift_report()["ok"]
