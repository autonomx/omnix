"""Compatibility installation for the legacy chat-session callback contract.

Production settings and secrets are no longer installed through app.shared.
They are owned by app.config.access / SettingsService. This shim remains only
for legacy session callers while those imports are retired.
"""
from .runtime import ensure_postgresql_runtime_ready

_INSTALLED = False


def install_postgresql_runtime_adapters() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_postgresql_runtime_ready()
    from app.chat.legacy_session_state import install_legacy_session_callbacks
    from .runtime_document_compat import (
        load_legacy_chat_sessions,
        save_legacy_chat_sessions,
        mutate_legacy_chat_sessions,
    )

    install_legacy_session_callbacks(
        load_callback=load_legacy_chat_sessions,
        save_callback=save_legacy_chat_sessions,
        update_callback=mutate_legacy_chat_sessions,
    )
    _INSTALLED = True


def uninstall_runtime_adapters_for_test() -> None:
    global _INSTALLED
    from app.chat.legacy_session_state import clear_legacy_session_callbacks

    clear_legacy_session_callbacks()
    _INSTALLED = False


def runtime_adapters_installed() -> bool:
    return _INSTALLED
