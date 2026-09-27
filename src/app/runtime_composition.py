"""Explicit production repository factories; no imported classes are replaced."""

from functools import lru_cache


@lru_cache(maxsize=1)
def production_job_store():
    from app.persistence.job_runtime_compat import PostgresJobStoreAdapter
    from app.jobs.rpg_turn_job_guard import install_rpg_turn_job_guard
    from app.jobs.rpg_debug_job_hook import install_rpg_debug_job_hook

    # Production feature work is claimed by the leased durable feature worker.
    # Keep only the non-execution RPG compatibility guards until those callers
    # migrate to explicit repository services.
    install_rpg_turn_job_guard(PostgresJobStoreAdapter)
    install_rpg_debug_job_hook(PostgresJobStoreAdapter)
    return PostgresJobStoreAdapter()


@lru_cache(maxsize=1)
def production_asset_store():
    from app.persistence.asset_compat import PostgresSharedAssetStoreAdapter
    return PostgresSharedAssetStoreAdapter()


def production_chat_store():
    from app.chat.persistence.chat_runtime_compat import default_chat_store, PostgresCharacterChatSessionStore
    from app.chat.live_agent_store import install_live_agent_store_hooks
    install_live_agent_store_hooks(PostgresCharacterChatSessionStore, PostgresCharacterChatSessionStore)
    return default_chat_store()


@lru_cache(maxsize=1)
def production_model_residency_store():
    from app.persistence.execution_feature_compat import PostgresModelResidencyStore
    return PostgresModelResidencyStore()


@lru_cache(maxsize=1)
def production_provider_refresh_store():
    from app.persistence.execution_feature_compat import PostgresProviderModelRefreshStore
    return PostgresProviderModelRefreshStore()


def production_character_repository():
    from app.characters.persistence.character_compat import PostgresCharacterRepositoryAdapter
    return PostgresCharacterRepositoryAdapter()


def production_avatar_repository():
    from app.characters.persistence.avatar_compat import PostgresCharacterAvatarRepositoryAdapter
    return PostgresCharacterAvatarRepositoryAdapter()


def production_memory_repository():
    from app.assistant_memory.persistence.memory_compat import PostgresMemoryRepositoryAdapter
    return PostgresMemoryRepositoryAdapter()


def production_owner_memory_repository():
    from app.assistant_memory.persistence.owner_memory_compat import PostgresOwnerAwareMemoryRepository
    return PostgresOwnerAwareMemoryRepository()


@lru_cache(maxsize=1)
def production_memory_settings_store():
    from app.persistence.runtime_document_compat import postgres_assistant_memory_settings_store_class
    return postgres_assistant_memory_settings_store_class()()


@lru_cache(maxsize=1)
def production_conversation_profile_store():
    from app.persistence.runtime_document_compat import default_postgres_live_conversation_profile_store
    return default_postgres_live_conversation_profile_store()


@lru_cache(maxsize=1)
def production_evaluation_store():
    from app.persistence.document_feature_compat import PostgresLiveChatEvaluationStore
    return PostgresLiveChatEvaluationStore()


@lru_cache(maxsize=1)
def production_research_source_store():
    from app.persistence.document_feature_compat import PostgresResearchSourceStore
    return PostgresResearchSourceStore()


def production_summary_repository():
    from app.chat.persistence.chat_runtime_compat import PostgresConversationSummaryRepository
    return PostgresConversationSummaryRepository()


def production_narrative_store(*args, **kwargs):
    from app.rpg.persistence.rpg_feature_compat import PostgresNarrativeEventStore
    return PostgresNarrativeEventStore(*args, **kwargs)