from __future__ import annotations

import sqlite3
from functools import lru_cache
from typing import Any

from .asset_compat import PostgresSharedAssetStoreAdapter
from .character_compat import PostgresCharacterRepositoryAdapter
from .chat_compat import PostgresChatRepositoryAdapter
from .foreground_submission_compat import (
    PostgresForegroundSubmissionStoreAdapter,
    submission_store_for_job_store as postgres_submission_store_for_job_store,
)
from .job_runtime_compat import PostgresJobStoreAdapter
from .memory_compat import PostgresMemoryRepositoryAdapter
from .rpg_compat import (
    append_interaction_event_postgres,
    archive_session_in_postgres,
    compact_interaction_events_postgres,
    interaction_log_status_postgres,
    list_sessions_from_postgres,
    load_interaction_events_postgres,
    load_session_from_postgres,
    save_session_to_postgres,
)
from .runtime import LegacyPersistenceRetired, ensure_postgresql_runtime_ready


_INSTALLED = False
_ORIGINAL_SQLITE_CONNECT = sqlite3.connect


def _retired_sqlite_connect(*args: Any, **kwargs: Any) -> Any:
    del args, kwargs
    raise LegacyPersistenceRetired(
        "SQLite runtime access is retired. Use PostgreSQL or an explicit Phase 8 "
        "legacy import/test process."
    )


def install_postgresql_runtime_adapters() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_postgresql_runtime_ready()

    # Fail closed before importing feature modules. Any missed legacy path cannot
    # silently become authoritative after PostgreSQL activation.
    sqlite3.connect = _retired_sqlite_connect  # type: ignore[assignment]

    from app import assets as assets_package
    from app.assets import store as asset_store_module
    from app.assistant_memory import service as memory_service_module
    from app.characters import service as character_service_module
    from app.characters import repository as character_repository_module
    from app.chat import repository as chat_repository_module
    from app.chat import store as chat_store_module
    from app.jobs import rpg_foreground_submission_store as submission_store_module
    from app.jobs import store as job_store_module
    import app.jobs as jobs_package
    from app.rpg.session import durable_store as durable_store_module
    from app.rpg.session import interaction_event_store as interaction_store_module
    from app.rpg.session import service as session_service_module
    import app.rpg.session as session_package

    chat_repository_module.SQLiteChatRepository = PostgresChatRepositoryAdapter
    chat_store_module.SQLiteChatRepository = PostgresChatRepositoryAdapter

    memory_service_module.SQLiteMemoryRepository = PostgresMemoryRepositoryAdapter

    character_repository_module.CharacterRepository = PostgresCharacterRepositoryAdapter
    character_service_module.CharacterRepository = PostgresCharacterRepositoryAdapter

    asset_store_module.SharedAssetStore = PostgresSharedAssetStoreAdapter
    assets_package.SharedAssetStore = PostgresSharedAssetStoreAdapter

    @lru_cache(maxsize=1)
    def _default_postgres_job_store() -> PostgresJobStoreAdapter:
        return PostgresJobStoreAdapter()

    job_store_module.default_job_store = _default_postgres_job_store
    jobs_package.default_job_store = _default_postgres_job_store

    submission_store_module.RpgForegroundSubmissionStore = (
        PostgresForegroundSubmissionStoreAdapter
    )
    submission_store_module.submission_store_for_job_store = (
        postgres_submission_store_for_job_store
    )

    durable_store_module.save_session_to_disk = save_session_to_postgres
    durable_store_module.load_session_from_disk = load_session_from_postgres
    durable_store_module.list_sessions_from_disk = list_sessions_from_postgres
    durable_store_module.archive_session_on_disk = archive_session_in_postgres

    session_service_module.save_session_to_disk = save_session_to_postgres
    session_service_module.load_session_from_disk = load_session_from_postgres
    session_service_module.list_sessions_from_disk = list_sessions_from_postgres
    session_service_module.archive_session_on_disk = archive_session_in_postgres

    session_package.save_session_to_disk = save_session_to_postgres
    session_package.load_session_from_disk = load_session_from_postgres
    session_package.list_sessions_from_disk = list_sessions_from_postgres
    session_package.archive_session_on_disk = archive_session_in_postgres

    interaction_store_module.append_interaction_event = append_interaction_event_postgres
    interaction_store_module.load_interaction_events = load_interaction_events_postgres
    interaction_store_module.compact_interaction_event_log = compact_interaction_events_postgres
    interaction_store_module.interaction_event_log_status = interaction_log_status_postgres

    _INSTALLED = True


def uninstall_runtime_adapters_for_test() -> None:
    global _INSTALLED
    sqlite3.connect = _ORIGINAL_SQLITE_CONNECT  # type: ignore[assignment]
    _INSTALLED = False


def runtime_adapters_installed() -> bool:
    return _INSTALLED
