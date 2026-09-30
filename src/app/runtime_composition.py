"""Explicit production repository factories; no imported classes are replaced."""

from functools import lru_cache


def _register_feature_repositories(feature_id: str) -> None:
    from app.persistence.repository_registry import install_repository_specs
    from app.runtime.feature_catalog import load_feature

    feature = load_feature(feature_id)
    install_repository_specs(tuple(feature.repositories))


@lru_cache(maxsize=1)
def production_job_store():
    from app.chat.persistence.job_store import PostgresJobStoreAdapter

    # Feature execution and submission policy are registry-owned.
    return PostgresJobStoreAdapter()


@lru_cache(maxsize=1)
def production_asset_store():
    from app.persistence.asset_compat import PostgresSharedAssetStoreAdapter
    return PostgresSharedAssetStoreAdapter()


def production_chat_store():
    _register_feature_repositories("chat")
    from app.chat.persistence.chat_runtime_compat import (
        PostgresCharacterChatSessionStore,
        default_chat_store,
    )
    from app.chat.live_agent_store import install_live_agent_store_hooks
    from app.assistant_memory import default_memory_service
    from app.assistant_memory.settings import load_memory_runtime_settings
    from app.desktop_companion.chat_activity import record_accepted_chat_activity
    from app.live_voice.chat_integration import create_live_voice_chat_port

    install_live_agent_store_hooks(
        PostgresCharacterChatSessionStore,
    )
    return default_chat_store(
        store_class=PostgresCharacterChatSessionStore,
        memory_service_factory=default_memory_service,
        memory_settings_factory=load_memory_runtime_settings,
        job_service=production_job_store(),
        live_voice_chat_port=create_live_voice_chat_port(),
        accepted_chat_activity_recorder=record_accepted_chat_activity,
    )


@lru_cache(maxsize=1)
def production_model_residency_store():
    from app.persistence.model_residency import PostgresModelResidencyStore
    return PostgresModelResidencyStore()


@lru_cache(maxsize=1)
def production_provider_refresh_store():
    from app.providers.persistence.model_refresh import PostgresProviderModelRefreshStore
    return PostgresProviderModelRefreshStore()


def production_character_repository():
    _register_feature_repositories("characters")
    from app.characters.persistence.character_compat import PostgresCharacterRepositoryAdapter
    return PostgresCharacterRepositoryAdapter()


def production_avatar_repository():
    _register_feature_repositories("characters")
    from app.characters.persistence.avatar_compat import PostgresCharacterAvatarRepositoryAdapter
    return PostgresCharacterAvatarRepositoryAdapter()


def production_memory_repository():
    _register_feature_repositories("assistant-memory")
    from app.assistant_memory.persistence.memory_compat import PostgresMemoryRepositoryAdapter
    return PostgresMemoryRepositoryAdapter()


def production_owner_memory_repository():
    _register_feature_repositories("assistant-memory")
    from app.assistant_memory.persistence.owner_memory_compat import PostgresOwnerAwareMemoryRepository
    return PostgresOwnerAwareMemoryRepository()


@lru_cache(maxsize=1)
def production_memory_settings_store():
    from app.assistant_memory.persistence.settings_store import SettingsServiceAssistantMemorySettingsStore
    from app.settings.access import current_settings_service
    return SettingsServiceAssistantMemorySettingsStore(current_settings_service())


@lru_cache(maxsize=1)
def production_conversation_profile_store():
    _register_feature_repositories("characters")
    from app.characters.persistence.live_profile_store import PostgresLiveConversationProfileStore
    return PostgresLiveConversationProfileStore()


@lru_cache(maxsize=1)
def production_evaluation_store():
    _register_feature_repositories("chat")
    from app.chat.persistence.evaluation_store import PostgresLiveChatEvaluationStore
    return PostgresLiveChatEvaluationStore()


@lru_cache(maxsize=1)
def production_research_source_store():
    _register_feature_repositories("research")
    from app.research.persistence.source_store import PostgresResearchSourceStore
    return PostgresResearchSourceStore()


def production_summary_repository():
    _register_feature_repositories("chat")
    from app.chat.persistence.chat_runtime_compat import PostgresConversationSummaryRepository
    return PostgresConversationSummaryRepository()


def production_narrative_store(*args, **kwargs):
    _register_feature_repositories("rpg")
    from app.rpg.persistence.rpg_feature_compat import PostgresNarrativeEventStore
    return PostgresNarrativeEventStore(*args, **kwargs)
