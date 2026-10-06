"""Controlled synthetic fixtures for the Stage 2 read-only pilot."""
from __future__ import annotations

from typing import Any

from .stage2_contracts import Stage2PrepareConfig, marker_memory
from .stage2_http import Stage2Gateway


def ensure_character(
    gateway: Stage2Gateway,
    character_id: str,
    display_name: str,
) -> dict[str, Any]:
    existing = next(
        (item for item in gateway.list_characters() if item.get("id") == character_id),
        None,
    )
    if existing is not None:
        if existing.get("status") == "archived":
            raise RuntimeError(f"Stage 2 character is archived: {character_id}")
        return existing
    return gateway.create_character(
        {
            "id": character_id,
            "display_name": display_name,
            "description": "Synthetic Character Mode Stage 2 isolation fixture.",
            "personality_prompt": (
                "Be concise and clear. Remain an AI character. Treat approved memory as background context only."
            ),
            "default_greeting": f"{display_name} Stage 2 fixture ready.",
            "speech_style": {
                "speed": 1.0,
                "temperature": 0.4,
                "top_k": 20,
                "top_p": 0.8,
                "repetition_penalty": 1.0,
                "expressiveness": "neutral",
                "default_emotion": "calm",
                "interruption_style": "balanced",
            },
            "identity_policy": {
                "may_claim_to_be_human": False,
                "may_claim_real_world_experiences": False,
                "disclosure_required": True,
            },
            "shared_memory_policy": {"access": "none", "allowed_categories": []},
            "enabled": True,
        }
    )


def create_character_session(
    gateway: Stage2Gateway,
    config: Stage2PrepareConfig,
    *,
    character_id: str,
    title: str,
    read_memory: bool,
    write_memory: bool,
) -> dict[str, Any]:
    return gateway.create_session(
        {
            "title": title,
            "provider_id": config.provider_id,
            "model_id": config.model_id,
            "interaction_mode": "character",
            "character_id": character_id,
            "read_memory": read_memory,
            "write_memory": write_memory,
            "shared_memory_access": "none",
            "transcript_policy": "persistent",
        }
    )


def create_system_setup_session(
    gateway: Stage2Gateway,
    config: Stage2PrepareConfig,
) -> dict[str, Any]:
    return gateway.create_session(
        {
            "title": "Stage 2 System Assistant memory fixture",
            "provider_id": config.provider_id,
            "model_id": config.model_id,
            "interaction_mode": "system",
            "read_memory": False,
            "write_memory": False,
            "shared_memory_access": "none",
            "transcript_policy": "persistent",
        }
    )


def ensure_synthetic_memory(
    gateway: Stage2Gateway,
    *,
    session_id: str,
    run_id: str,
    owner_label: str,
) -> dict[str, Any]:
    content = marker_memory(run_id, owner_label)
    existing = gateway.list_memory(session_id)
    records = existing.get("records") if isinstance(existing.get("records"), list) else []
    matches = [
        item
        for item in records
        if isinstance(item, dict)
        and item.get("content") == content
        and item.get("status") == "active"
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"duplicate active Stage 2 fixture memories exist for {owner_label}; clean them before rerunning"
        )
    if matches:
        return matches[0]
    return gateway.create_memory(
        {
            "session_id": session_id,
            "scope": "global",
            "category": "relationship",
            "content": content,
            "pinned": True,
        }
    )


def memory_record_ids(payload: dict[str, Any]) -> list[str]:
    records = payload.get("records")
    if not isinstance(records, list):
        return []
    return sorted(
        str(item.get("id"))
        for item in records
        if isinstance(item, dict) and item.get("id")
    )


def memory_candidate_ids(payload: dict[str, Any]) -> list[str]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return []
    return sorted(
        str(item.get("id"))
        for item in candidates
        if isinstance(item, dict) and item.get("id")
    )


def snapshot_item_ids(state: dict[str, Any], *, active_only: bool = True) -> list[str]:
    snapshot = state.get("snapshot")
    if not isinstance(snapshot, dict):
        return []
    items = snapshot.get("items")
    if not isinstance(items, list):
        return []
    values = []
    for item in items:
        if not isinstance(item, dict) or not item.get("memory_record_id"):
            continue
        if active_only and not item.get("active"):
            continue
        values.append(str(item["memory_record_id"]))
    return sorted(values)


__all__ = [
    "create_character_session",
    "create_system_setup_session",
    "ensure_character",
    "ensure_synthetic_memory",
    "memory_candidate_ids",
    "memory_record_ids",
    "snapshot_item_ids",
]
