"""Explicit production factories that wire several features together.

Each feature owns the factory for its own repositories (ADR-0016, PA-1.2);
only cross-feature wiring and kernel stores composed with feature adapters
remain here, and only composition imports this module.
"""

from app.caching.bounded_cache import bounded_lru_cache
from app.persistence.repository_registry import register_feature_repositories


def production_job_store(
    *,
    database=None,
    context=None,
    chat_execution_owner=None,
    chat_dispatcher=None,
):
    from app.chat.persistence.job_store import PostgresJobStoreAdapter

    if all(
        value is None
        for value in (database, context, chat_execution_owner, chat_dispatcher)
    ):
        return _default_production_job_store()
    # Feature execution and submission policy are registry-owned.
    return PostgresJobStoreAdapter(
        database=database,
        context=context,
        chat_execution_owner=chat_execution_owner,
        chat_dispatcher=chat_dispatcher,
    )


@bounded_lru_cache(max_entries=1, ttl_seconds=3600.0)
def _default_production_job_store():
    from app.chat.persistence.job_store import PostgresJobStoreAdapter

    return PostgresJobStoreAdapter()


def production_chat_store(*, job_service=None, live_agent_planner=None):
    register_feature_repositories("chat")
    from app.chat.persistence.chat_runtime import (
        PostgresCharacterChatSessionStore,
        default_chat_store,
    )
    from app.chat.live_agent_store import default_live_agent_planner
    from app.assistant_memory import default_memory_service
    from app.assistant_memory.settings import load_memory_runtime_settings
    from app.desktop_companion.chat_activity import record_accepted_chat_activity
    from app.live_voice.chat_integration import create_live_voice_chat_port

    if job_service is None:
        job_service = production_job_store()
    if live_agent_planner is None:
        live_agent_planner = default_live_agent_planner()
    return default_chat_store(
        store_class=PostgresCharacterChatSessionStore,
        memory_service_factory=default_memory_service,
        memory_settings_factory=load_memory_runtime_settings,
        job_service=job_service,
        live_voice_chat_port=create_live_voice_chat_port(),
        live_agent_planner=live_agent_planner,
        accepted_chat_activity_recorder=record_accepted_chat_activity,
    )


def composition_port_bindings():
    """Ports only the composition root can bind (exactly-one; ADR-0016)."""
    from app.chat.character_store import CHAT_STORE_FACTORY
    from app.runtime.ports import PortBinding

    return [PortBinding(CHAT_STORE_FACTORY, production_chat_store)]


@bounded_lru_cache(max_entries=1, ttl_seconds=3600.0)
def production_model_residency_store():
    from app.persistence.model_residency import PostgresModelResidencyStore
    return PostgresModelResidencyStore()


def production_owner_memory_repository():
    """Imported only when the memory service first needs a repository."""
    from app.assistant_memory.persistence.owner_memory_store import (
        production_owner_memory_repository as owner_memory_repository,
    )

    return owner_memory_repository()
