"""Thin FastAPI gateway foundation for the Omnix web app redesign."""

from __future__ import annotations

from app.rpg.jobs.turn_job_mirror import install_rpg_turn_job_mirror_hook


def _install_required_rpg_turn_hooks() -> None:
    from app.rpg.session import interactive_first_call_runtime
    from app.rpg.session.dialogue_quality_hook import install_dialogue_quality_hook
    from app.rpg.session.fast_visible_dialogue_hook import (
        install_fast_visible_dialogue_hook,
    )
    from app.rpg.session.interaction_lifecycle_hook import (
        install_interaction_lifecycle_hook,
    )
    from app.rpg.session.interaction_timeline_hook import (
        install_interaction_timeline_hook,
    )

    install_fast_visible_dialogue_hook()
    install_dialogue_quality_hook()
    install_interaction_timeline_hook()
    install_interaction_lifecycle_hook()
    if not getattr(
        interactive_first_call_runtime,
        "_omnix_fast_visible_dialogue_hook_installed",
        False,
    ):
        raise RuntimeError("RPG fast visible dialogue hook failed to install")
    if not getattr(
        interactive_first_call_runtime, "_omnix_dialogue_quality_hook_installed", False
    ):
        raise RuntimeError("RPG dialogue quality hook failed to install")
    if not getattr(
        interactive_first_call_runtime,
        "_omnix_interaction_timeline_hook_installed",
        False,
    ):
        raise RuntimeError("RPG interaction timeline hook failed to install")
    if not getattr(
        interactive_first_call_runtime,
        "_omnix_interaction_lifecycle_runtime_hook_installed",
        False,
    ):
        raise RuntimeError("RPG interaction lifecycle runtime hook failed to install")
    install_rpg_turn_job_mirror_hook()
