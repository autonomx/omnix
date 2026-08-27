from __future__ import annotations

import sqlite3
import sys
from functools import lru_cache
from typing import Any

from .asset_compat import PostgresSharedAssetStoreAdapter
from .avatar_compat import PostgresCharacterAvatarRepositoryAdapter
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
    list_session_summaries_from_postgres,
    save_session_to_postgres,
)
from .runtime import LegacyPersistenceRetired, ensure_postgresql_runtime_ready


_INSTALLED = False
_ORIGINAL_SQLITE_CONNECT = sqlite3.connect


def _retired_sqlite_connect(*args: Any, **kwargs: Any) -> Any:
    del args, kwargs
    raise LegacyPersistenceRetired(
        "SQLite runtime access is retired. Use PostgreSQL or an explicit legacy "
        "import/test process."
    )


def install_postgresql_runtime_adapters() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_postgresql_runtime_ready()

    # Fail closed before importing feature modules. Any missed legacy path cannot
    # silently become authoritative after PostgreSQL activation.
    sqlite3.connect = _retired_sqlite_connect  # type: ignore[assignment]

    _install_remaining_document_authority_adapters()
    _install_core_domain_adapters()
    _install_chat_runtime()
    _install_execution_runtime()
    _install_feature_document_runtime()
    _install_rpg_runtime()
    _INSTALLED = True


def _install_remaining_document_authority_adapters() -> None:
    from app import shared
    from app.assist_core import house_state as house_state_module
    from app.assistant_memory import settings as memory_settings_module
    from app.assistant_tools import credentials as tool_credentials_module
    from app.assistant_tools import config_store as tool_config_module
    from app.assistant_tools import ledger as tool_ledger_module
    from app.characters import live_conversation_profile as conversation_profile_module

    from .runtime_document_compat import (
        append_assistant_tool_ledger_entry_postgres,
        default_postgres_live_conversation_profile_store,
        load_application_settings,
        load_assist_house_state,
        load_assistant_tool_ledger_postgres,
        load_empty_assistant_tool_credentials,
        load_empty_assistant_tool_oauth_clients,
        load_legacy_chat_sessions,
        mutate_legacy_chat_sessions,
        no_assistant_tool_credential,
        postgres_assistant_memory_settings_store_class,
        postgres_live_conversation_profile_store_class,
        save_application_settings,
        save_assist_house_state,
        save_legacy_chat_sessions,
        unavailable_assistant_tool_secret,
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
    house_state_module.load_house_state = load_assist_house_state
    house_state_module.save_house_state = save_assist_house_state
    memory_settings_module.AssistantMemorySettingsStore = (
        postgres_assistant_memory_settings_store_class()
    )
    conversation_profile_module.LiveConversationProfileStore = (
        postgres_live_conversation_profile_store_class()
    )
    conversation_profile_module.install_live_conversation_profile_store_factory(
        default_postgres_live_conversation_profile_store
    )
    tool_ledger_module.append_assistant_tool_ledger_entry = (
        append_assistant_tool_ledger_entry_postgres
    )
    tool_ledger_module.load_assistant_tool_ledger = load_assistant_tool_ledger_postgres
    tool_credentials_module.load_assistant_tool_credentials = (
        load_empty_assistant_tool_credentials
    )
    tool_credentials_module.load_assistant_tool_oauth_clients = (
        load_empty_assistant_tool_oauth_clients
    )
    tool_credentials_module.save_assistant_tool_credentials = (
        unavailable_assistant_tool_secret
    )
    tool_credentials_module.save_assistant_tool_oauth_clients = (
        unavailable_assistant_tool_secret
    )
    tool_credentials_module.credential_for_tool = no_assistant_tool_credential
    tool_credentials_module.oauth_client_for_provider = no_assistant_tool_credential
    tool_credentials_module.upsert_tool_credential = unavailable_assistant_tool_secret
    tool_credentials_module.upsert_oauth_client = unavailable_assistant_tool_secret
    tool_credentials_module.delete_tool_credential = no_assistant_tool_credential
    tool_config_module.delete_tool_credential = no_assistant_tool_credential
    secret_consumer_replacements = {
        "credential_for_tool": no_assistant_tool_credential,
        "oauth_client_for_provider": no_assistant_tool_credential,
        "upsert_tool_credential": unavailable_assistant_tool_secret,
        "upsert_oauth_client": unavailable_assistant_tool_secret,
    }
    for module_name in (
        "app.assistant_tools.connections",
        "app.assistant_tools.gmail_adapter",
    ):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for name, replacement in secret_consumer_replacements.items():
            if hasattr(module, name):
                setattr(module, name, replacement)
    for module_name in (
        "app.assistant_tools.capability_dashboard",
        "app.assistant_tools.hermes_bridge",
        "app.assistant_tools.routes",
    ):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        if hasattr(module, "append_assistant_tool_ledger_entry"):
            setattr(
                module,
                "append_assistant_tool_ledger_entry",
                append_assistant_tool_ledger_entry_postgres,
            )
        if hasattr(module, "load_assistant_tool_ledger"):
            setattr(
                module,
                "load_assistant_tool_ledger",
                load_assistant_tool_ledger_postgres,
            )


def _install_core_domain_adapters() -> None:
    from app import assets as assets_package
    from app.assets import store as asset_store_module
    from app.assistant_memory import service as memory_service_module
    from app.characters import repository as character_repository_module
    from app.characters import avatar_repository as avatar_repository_module
    from app.characters import avatar_service as avatar_service_module
    from app.characters import service as character_service_module
    from app.chat import repository as chat_repository_module

    chat_repository_module.InMemoryChatRepository = PostgresChatRepositoryAdapter
    memory_service_module.InMemoryMemoryRepository = PostgresMemoryRepositoryAdapter
    character_repository_module.CharacterRepository = PostgresCharacterRepositoryAdapter
    character_service_module.CharacterRepository = PostgresCharacterRepositoryAdapter
    avatar_repository_module.CharacterAvatarRepository = (
        PostgresCharacterAvatarRepositoryAdapter
    )
    avatar_service_module.CharacterAvatarRepository = (
        PostgresCharacterAvatarRepositoryAdapter
    )
    asset_store_module.SharedAssetStore = PostgresSharedAssetStoreAdapter
    assets_package.SharedAssetStore = PostgresSharedAssetStoreAdapter


def _install_chat_runtime() -> None:
    import app.chat as chat_package
    from app.chat import assistant_turns as assistant_turns_module
    from app.chat import character_store as character_store_module
    from app.chat import compaction as compaction_module
    from app.chat import history_search as history_module
    from app.chat import prompt_store as prompt_store_module
    from app.chat import store as base_store_module
    from app.chat.live_agent_store import install_live_agent_store_hooks

    from .chat_runtime_compat import (
        PostgresCharacterChatSessionStore,
        PostgresChatSessionStore,
        PostgresConversationSummaryRepository,
        PostgresHistorySearchService,
        default_chat_store,
        default_history_search_service,
    )
    from .runtime_document_compat import postgres_assistant_turn_coordinator_class

    assistant_turns_module.AssistantTurnCoordinator = (
        postgres_assistant_turn_coordinator_class()
    )
    assistant_turns_module._default_coordinator = None

    prompt_store_module.ChatSessionStore = PostgresChatSessionStore
    base_store_module.ChatSessionStore = PostgresChatSessionStore
    character_store_module.ChatSessionStore = PostgresCharacterChatSessionStore
    character_store_module.InMemoryChatSessionStore = PostgresCharacterChatSessionStore
    character_store_module.default_chat_store = default_chat_store
    chat_package.ChatSessionStore = PostgresCharacterChatSessionStore
    chat_package.InMemoryChatSessionStore = PostgresCharacterChatSessionStore
    chat_package.default_chat_store = default_chat_store

    compaction_module.InMemoryConversationSummaryRepository = (
        PostgresConversationSummaryRepository
    )
    history_module.InMemoryHistorySearchService = PostgresHistorySearchService
    history_module.default_history_search_service = default_history_search_service

    install_live_agent_store_hooks(
        PostgresCharacterChatSessionStore,
        PostgresCharacterChatSessionStore,
    )


def _install_execution_runtime() -> None:
    import app.jobs as jobs_package
    from app.jobs import image_inline
    from app.jobs import inline_feature_jobs
    from app.jobs import research_inline
    from app.jobs import residency as residency_module
    from app.jobs import rpg_debug_job_hook
    from app.jobs import rpg_turn_job_guard
    from app.jobs import store as job_store_module
    from app.jobs import voice_inline
    from app.jobs import rpg_foreground_submission_store as submission_store_module
    from app.providers import cache_status as cache_status_module

    from .execution_feature_compat import (
        PostgresModelResidencyStore,
        PostgresProviderModelRefreshStore,
    )

    def _skip_legacy_voice_manifest(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    @lru_cache(maxsize=1)
    def _default_postgres_job_store() -> PostgresJobStoreAdapter:
        return PostgresJobStoreAdapter()

    @lru_cache(maxsize=1)
    def _default_postgres_residency_store() -> PostgresModelResidencyStore:
        return PostgresModelResidencyStore()

    @lru_cache(maxsize=1)
    def _default_postgres_refresh_store() -> PostgresProviderModelRefreshStore:
        return PostgresProviderModelRefreshStore()

    job_store_module.InMemoryJobStore = PostgresJobStoreAdapter
    job_store_module.default_job_store = _default_postgres_job_store
    jobs_package.InMemoryJobStore = PostgresJobStoreAdapter
    jobs_package.default_job_store = _default_postgres_job_store

    residency_module.InMemoryModelResidencyStore = PostgresModelResidencyStore
    residency_module.default_model_residency_store = _default_postgres_residency_store
    jobs_package.InMemoryModelResidencyStore = PostgresModelResidencyStore
    jobs_package.default_model_residency_store = _default_postgres_residency_store

    cache_status_module.InMemoryProviderModelRefreshStore = PostgresProviderModelRefreshStore
    cache_status_module.default_provider_model_refresh_store = _default_postgres_refresh_store

    submission_store_module.RpgForegroundSubmissionStore = (
        PostgresForegroundSubmissionStoreAdapter
    )
    submission_store_module.submission_store_for_job_store = (
        postgres_submission_store_for_job_store
    )

    # Existing decorators were attached to the provider-free job class during
    # module import. Install the same deterministic handlers on the authoritative
    # PostgreSQL job facade before any worker is created.
    inline_feature_jobs.install_inline_feature_job_execution(PostgresJobStoreAdapter)
    rpg_turn_job_guard.install_rpg_turn_job_guard(PostgresJobStoreAdapter)
    voice_inline.install_voice_studio_job_execution(PostgresJobStoreAdapter)
    image_inline.install_image_job_execution(PostgresJobStoreAdapter)
    research_inline.install_research_job_execution(PostgresJobStoreAdapter)
    rpg_debug_job_hook.install_rpg_debug_job_hook(PostgresJobStoreAdapter)
    voice_inline._upsert_legacy_voice_manifest = _skip_legacy_voice_manifest


def _install_feature_document_runtime() -> None:
    from app.gateway import live_chat_evaluation_routes as evaluation_routes_module
    from app.assist_core import policy_store as policy_module
    from app.assistant_tools import config_store as tool_config_module
    from app.gateway import live_chat_evaluation_store as evaluation_module
    from app.image import asset_store as image_module
    from app.research import source_store as research_module

    from .configuration_compat import (
        add_assist_pending,
        append_assist_action_log,
        load_assistant_tools_config,
        read_assist_pending,
        save_assistant_tools_config,
        write_assist_pending,
    )
    from .document_feature_compat import (
        PostgresLiveChatEvaluationStore,
        PostgresResearchSourceStore,
    )
    from .image_asset_compat import (
        cleanup_unused_image_assets_postgres,
        delete_image_asset_postgres,
        get_image_asset_manifest_postgres,
        register_image_asset_file_postgres,
        save_image_asset_bytes_postgres,
    )

    policy_module.read_pending = read_assist_pending
    policy_module.write_pending = write_assist_pending
    policy_module.add_pending = add_assist_pending
    policy_module.append_log = append_assist_action_log

    tool_config_module.load_assistant_tools_config = load_assistant_tools_config
    tool_config_module.save_assistant_tools_config = save_assistant_tools_config

    @lru_cache(maxsize=1)
    def _default_evaluation_store() -> PostgresLiveChatEvaluationStore:
        return PostgresLiveChatEvaluationStore()

    evaluation_module.LiveChatEvaluationStore = PostgresLiveChatEvaluationStore
    evaluation_module.default_live_chat_evaluation_store = _default_evaluation_store
    evaluation_routes_module.LiveChatEvaluationStore = PostgresLiveChatEvaluationStore
    evaluation_routes_module.default_live_chat_evaluation_store = (
        _default_evaluation_store
    )

    @lru_cache(maxsize=1)
    def _default_research_store() -> PostgresResearchSourceStore:
        return PostgresResearchSourceStore()

    research_module.ResearchSourceStore = PostgresResearchSourceStore
    research_module.default_research_source_store = _default_research_store

    image_module.save_image_asset_bytes = save_image_asset_bytes_postgres
    image_module.register_image_asset_file = register_image_asset_file_postgres
    image_module.get_image_asset_manifest = get_image_asset_manifest_postgres
    image_module.delete_image_asset = delete_image_asset_postgres
    image_module.cleanup_unused_image_assets = cleanup_unused_image_assets_postgres


def _install_rpg_runtime() -> None:
    import app.rpg.session as session_package
    from app.rpg.narrative import narrative_persistence as narrative_module
    from app.rpg.npc_evolution import profile_store as profile_module
    from app.rpg.session import durable_store as durable_store_module
    from app.rpg.session import interaction_event_store as interaction_store_module
    from app.rpg.session import service as session_service_module

    from .rpg_feature_compat import (
        PostgresNarrativeEventStore,
        load_npc_evolution_profiles_for_runtime_postgres,
        load_npc_profile_postgres,
        persist_npc_evolution_profiles_postgres,
    )

    durable_store_module.save_session_to_disk = save_session_to_postgres
    durable_store_module.load_session_from_disk = load_session_from_postgres
    durable_store_module.list_sessions_from_disk = list_sessions_from_postgres
    durable_store_module.archive_session_on_disk = archive_session_in_postgres

    session_service_module.save_session_to_disk = save_session_to_postgres
    session_service_module.load_session_from_disk = load_session_from_postgres
    session_service_module.list_sessions_from_disk = list_sessions_from_postgres
    session_service_module.list_session_summaries_from_disk = (
        list_session_summaries_from_postgres
    )
    session_service_module.archive_session_on_disk = archive_session_in_postgres

    session_package.save_session_to_disk = save_session_to_postgres
    session_package.load_session_from_disk = load_session_from_postgres
    session_package.list_sessions_from_disk = list_sessions_from_postgres
    session_package.archive_session_on_disk = archive_session_in_postgres

    interaction_store_module.append_interaction_event = append_interaction_event_postgres
    interaction_store_module.load_interaction_events = load_interaction_events_postgres
    interaction_store_module.compact_interaction_event_log = compact_interaction_events_postgres
    interaction_store_module.interaction_event_log_status = interaction_log_status_postgres

    narrative_module.NarrativeEventStore = PostgresNarrativeEventStore
    profile_module.load_npc_profile = load_npc_profile_postgres
    profile_module.persist_npc_evolution_profiles = persist_npc_evolution_profiles_postgres
    profile_module.load_npc_evolution_profiles_for_runtime = (
        load_npc_evolution_profiles_for_runtime_postgres
    )


def uninstall_runtime_adapters_for_test() -> None:
    global _INSTALLED
    from app import shared
    from app.characters import live_conversation_profile as conversation_profile_module

    sqlite3.connect = _ORIGINAL_SQLITE_CONNECT  # type: ignore[assignment]
    shared.clear_postgresql_document_callbacks()
    conversation_profile_module.clear_live_conversation_profile_store_factory()
    _INSTALLED = False


def runtime_adapters_installed() -> bool:
    return _INSTALLED
