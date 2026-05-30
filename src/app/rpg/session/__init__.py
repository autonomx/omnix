"""Phase 13.5 + 15.0 — Session lifecycle + persistence module."""
# Phase 15.0 — Durable persistence
from .durable_store import (
    list_sessions_from_disk,
    load_session_from_disk,
    save_session_to_disk,
)
from .session_store import (
    archive_session,
    ensure_session_registry,
    get_session,
    list_sessions,
    save_session,
)


def _install_optional_fast_runtime_hooks() -> None:
    try:
        from .fast_combat_narration_skip import install_fast_combat_narration_skip

        install_fast_combat_narration_skip()
    except Exception:
        # Runtime hook installation must never block normal session imports.
        return


_install_optional_fast_runtime_hooks()

__all__ = [
    "archive_session",
    "ensure_session_registry",
    "get_session",
    "list_sessions",
    "save_session",
    # Phase 15.0
    "list_sessions_from_disk",
    "load_session_from_disk",
    "save_session_to_disk",
]
