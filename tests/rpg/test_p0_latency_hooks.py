from __future__ import annotations


def test_p0_latency_hooks_are_present() -> None:
    import app.rpg.session  # noqa: F401
    from app.rpg.session import interactive_first_call_runtime as runtime

    assert getattr(runtime, "_omnix_fast_visible_dialogue_hook_installed", False) is True
    assert getattr(runtime, "_omnix_visible_response_runtime_guard_installed", False) is True
