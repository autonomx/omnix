from __future__ import annotations


def test_player_action_context_router_imports_without_legacy_session_store() -> None:
    import app.rpg.api.player_action_context as module

    assert module.router.prefix == "/api/rpg/player_action_context"
    assert callable(module.player_action_context_payload)
    assert module.load_session.__module__ == "app.rpg.session.service"


def test_player_action_context_source_uses_canonical_session_service() -> None:
    import inspect

    import app.rpg.api.player_action_context as module

    source = inspect.getsource(module)
    assert "app.rpg.session_store" not in source
    assert "from app.rpg.session.service import load_session" in source
