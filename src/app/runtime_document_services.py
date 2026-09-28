"""Immutable composition of document-domain operations during persistence retirement.

Callers depend on these behavioral contracts; PostgreSQL adapters are selected
only here. No request transaction or imported module is mutated by this object.
"""
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


@dataclass(frozen=True, slots=True)
class DocumentServices:
    list_session_summaries: Callable[..., Any]
    load_house_state: Callable[..., Any]
    save_house_state: Callable[..., Any]
    append_assistant_tool_ledger_entry: Callable[..., Any]
    load_assistant_tool_ledger: Callable[..., Any]
    load_assistant_tool_credentials: Callable[..., Any]
    load_assistant_tool_oauth_clients: Callable[..., Any]
    save_assistant_tool_credentials: Callable[..., Any]
    save_assistant_tool_oauth_clients: Callable[..., Any]
    credential_for_tool: Callable[..., Any]
    oauth_client_for_provider: Callable[..., Any]
    upsert_tool_credential: Callable[..., Any]
    upsert_oauth_client: Callable[..., Any]
    delete_tool_credential: Callable[..., Any]
    read_pending: Callable[..., Any]
    write_pending: Callable[..., Any]
    add_pending: Callable[..., Any]
    append_log: Callable[..., Any]
    load_assistant_tools_config: Callable[..., Any]
    save_assistant_tools_config: Callable[..., Any]
    save_image_asset_bytes: Callable[..., Any]
    register_image_asset_file: Callable[..., Any]
    get_image_asset_manifest: Callable[..., Any]
    delete_image_asset: Callable[..., Any]
    cleanup_unused_image_assets: Callable[..., Any]
    save_session_to_disk: Callable[..., Any]
    load_session_from_disk: Callable[..., Any]
    list_sessions_from_disk: Callable[..., Any]
    archive_session_on_disk: Callable[..., Any]
    append_interaction_event: Callable[..., Any]
    load_interaction_events: Callable[..., Any]
    compact_interaction_event_log: Callable[..., Any]
    interaction_event_log_status: Callable[..., Any]
    load_npc_profile: Callable[..., Any]
    persist_npc_evolution_profiles: Callable[..., Any]
    load_npc_evolution_profiles_for_runtime: Callable[..., Any]


@lru_cache(maxsize=1)
def production_document_services() -> DocumentServices:
    from app.assistant_tools.persistence import configuration
    from app.assistant_tools.persistence import runtime_documents as assistant_tool_documents
    from app.assist_core.persistence import house_state as assist_house_state
    from app.image.persistence import asset_compat as image_asset_compat
    from app.rpg.persistence import rpg_compat
    from app.rpg.persistence import rpg_feature_compat
    return DocumentServices(
        list_session_summaries=rpg_compat.list_session_summaries_from_postgres,
        load_house_state=assist_house_state.load_house_state_postgres,
        save_house_state=assist_house_state.save_house_state_postgres,
        append_assistant_tool_ledger_entry=assistant_tool_documents.append_assistant_tool_ledger_entry_postgres,
        load_assistant_tool_ledger=assistant_tool_documents.load_assistant_tool_ledger_postgres,
        load_assistant_tool_credentials=assistant_tool_documents.load_empty_assistant_tool_credentials,
        load_assistant_tool_oauth_clients=assistant_tool_documents.load_empty_assistant_tool_oauth_clients,
        save_assistant_tool_credentials=assistant_tool_documents.unavailable_assistant_tool_secret,
        save_assistant_tool_oauth_clients=assistant_tool_documents.unavailable_assistant_tool_secret,
        credential_for_tool=assistant_tool_documents.no_assistant_tool_credential,
        oauth_client_for_provider=assistant_tool_documents.no_assistant_tool_credential,
        upsert_tool_credential=assistant_tool_documents.unavailable_assistant_tool_secret,
        upsert_oauth_client=assistant_tool_documents.unavailable_assistant_tool_secret,
        delete_tool_credential=assistant_tool_documents.no_assistant_tool_credential,
        read_pending=configuration.read_assist_pending,
        write_pending=configuration.write_assist_pending,
        add_pending=configuration.add_assist_pending,
        append_log=configuration.append_assist_action_log,
        load_assistant_tools_config=configuration.load_assistant_tools_config,
        save_assistant_tools_config=configuration.save_assistant_tools_config,
        save_image_asset_bytes=image_asset_compat.save_image_asset_bytes_postgres,
        register_image_asset_file=image_asset_compat.register_image_asset_file_postgres,
        get_image_asset_manifest=image_asset_compat.get_image_asset_manifest_postgres,
        delete_image_asset=image_asset_compat.delete_image_asset_postgres,
        cleanup_unused_image_assets=image_asset_compat.cleanup_unused_image_assets_postgres,
        save_session_to_disk=rpg_compat.save_session_to_postgres,
        load_session_from_disk=rpg_compat.load_session_from_postgres,
        list_sessions_from_disk=rpg_compat.list_sessions_from_postgres,
        archive_session_on_disk=rpg_compat.archive_session_in_postgres,
        append_interaction_event=rpg_compat.append_interaction_event_postgres,
        load_interaction_events=rpg_compat.load_interaction_events_postgres,
        compact_interaction_event_log=rpg_compat.compact_interaction_events_postgres,
        interaction_event_log_status=rpg_compat.interaction_log_status_postgres,
        load_npc_profile=rpg_feature_compat.load_npc_profile_postgres,
        persist_npc_evolution_profiles=rpg_feature_compat.persist_npc_evolution_profiles_postgres,
        load_npc_evolution_profiles_for_runtime=rpg_feature_compat.load_npc_evolution_profiles_for_runtime_postgres,
    )
