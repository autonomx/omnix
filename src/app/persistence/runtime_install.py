"""Migration-only installation of shared.py's legacy document callback contract.

Domain dependencies use explicit factories. This shim never replaces imported
classes/functions or mutates sqlite3. Retire it when shared.py accepts a service.
"""
from .runtime import ensure_postgresql_runtime_ready

_INSTALLED = False


def install_postgresql_runtime_adapters() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_postgresql_runtime_ready()
    from app import shared
    from .runtime_document_compat import (
        load_application_settings, save_application_settings,
        load_legacy_chat_sessions, save_legacy_chat_sessions, mutate_legacy_chat_sessions,
    )
    from .provider_secret_store import load_provider_secrets, save_provider_secrets

    shared.install_postgresql_document_callbacks(
        load_settings_callback=load_application_settings,
        save_settings_callback=save_application_settings,
        load_sessions_callback=load_legacy_chat_sessions,
        save_sessions_callback=save_legacy_chat_sessions,
        load_secrets_callback=load_provider_secrets,
        save_secrets_callback=save_provider_secrets,
        update_sessions_callback=mutate_legacy_chat_sessions,
    )
    _INSTALLED = True


def uninstall_runtime_adapters_for_test() -> None:
    global _INSTALLED
    from app import shared
    shared.clear_postgresql_document_callbacks()
    _INSTALLED = False


def runtime_adapters_installed() -> bool:
    return _INSTALLED
