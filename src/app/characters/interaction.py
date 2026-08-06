"""Pure server-side Character Mode identity resolution."""
from __future__ import annotations

import hashlib
import json
import os

from .models import (
    SYSTEM_ASSISTANT_ID,
    SYSTEM_ASSISTANT_IDENTITY,
    SYSTEM_ASSISTANT_NAME,
    CharacterProfileSnapshot,
    InteractionSelection,
    ResolvedInteractionContext,
)

LEGACY_MAYA_SYSTEM_PROMPT = (
    "You are Maya, a warm, friendly, emotionally aware AI. Keep responses short "
    "(1-3 sentences for voice, 5 for text), match the user's emotional tone, avoid "
    "filler and tangents. Be clear and concise, admit uncertainty when needed, and "
    "maintain a natural, human-like presence."
)
_ALLOWED_SHARED_CATEGORIES = {"preference", "fact", "project", "relationship", "instruction"}


class CharacterInteractionError(ValueError):
    """Base error for rejected character interaction selections."""


class CharacterModeDisabledError(CharacterInteractionError):
    pass


class CharacterResolutionError(CharacterInteractionError):
    pass


def _env_flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def character_mode_enabled() -> bool:
    return _env_flag("OMNIX_CHARACTER_MODE_ENABLED")


def character_memory_enabled() -> bool:
    return _env_flag("OMNIX_CHARACTER_MEMORY_ENABLED")


def character_shared_memory_enabled() -> bool:
    return _env_flag("OMNIX_CHARACTER_SHARED_MEMORY_ENABLED")


def character_hermes_sync_enabled() -> bool:
    return _env_flag("OMNIX_CHARACTER_HERMES_SYNC_ENABLED")


def resolve_shared_memory_categories(session: object) -> list[str]:
    """Resolve the server-owned System Assistant category allowlist for a session."""

    if getattr(session, "interaction_mode", "system") != "character":
        return []
    if getattr(session, "shared_memory_access", "none") != "read_only":
        return []
    if not character_shared_memory_enabled():
        raise CharacterInteractionError("shared character memory access is disabled")
    character_id = str(getattr(session, "character_id", "") or "")
    if not character_id:
        raise CharacterResolutionError("character session is missing character_id")
    try:
        from .service import default_character_service

        character = default_character_service().resolve_snapshot(character_id)
    except Exception as exc:
        raise CharacterResolutionError("persisted character profile could not be resolved") from exc
    return _validate_shared_memory_policy(character)


def neutralize_legacy_system_prompt(prompt: str) -> str:
    """Replace only the old built-in Maya default, preserving user custom prompts."""

    text = (prompt or "").strip()
    if text == LEGACY_MAYA_SYSTEM_PROMPT:
        return SYSTEM_ASSISTANT_IDENTITY
    return text or SYSTEM_ASSISTANT_IDENTITY


def _identity_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_shared_memory_policy(character: CharacterProfileSnapshot) -> list[str]:
    policy = dict(character.shared_memory_policy or {})
    if policy.get("access") != "read_only":
        raise CharacterInteractionError("character profile does not permit shared memory access")
    raw_categories = policy.get("allowed_categories") or []
    if not isinstance(raw_categories, list):
        raise CharacterInteractionError("character shared memory categories are invalid")
    categories = [str(value) for value in raw_categories if str(value) in _ALLOWED_SHARED_CATEGORIES]
    if not categories:
        raise CharacterInteractionError("character profile has no permitted shared memory categories")
    return sorted(set(categories))


def _validated_identity_policy(character: CharacterProfileSnapshot) -> dict[str, object]:
    policy = dict(character.identity_policy or {})
    if policy.get("may_claim_to_be_human") is True:
        raise CharacterInteractionError("character identity policy cannot permit human identity claims")
    if policy.get("may_claim_real_world_experiences") is True:
        raise CharacterInteractionError("character identity policy cannot permit real-world experience claims")
    if policy.get("disclosure_required") is False:
        raise CharacterInteractionError("character identity disclosure cannot be disabled")
    policy["may_claim_to_be_human"] = False
    policy["may_claim_real_world_experiences"] = False
    policy["disclosure_required"] = True
    return policy


def resolve_interaction_context(
    selection: InteractionSelection,
    *,
    character: CharacterProfileSnapshot | None = None,
) -> ResolvedInteractionContext:
    """Resolve an untrusted selection into a trusted, reproducible identity context."""

    if selection.interaction_mode == "system":
        if selection.character_id:
            raise CharacterResolutionError("system mode cannot select a character")
        payload = {
            "interaction_mode": "system",
            "owner_type": "system",
            "owner_id": SYSTEM_ASSISTANT_ID,
            "display_name": SYSTEM_ASSISTANT_NAME,
            "voice_asset_id": selection.voice_asset_id,
            "read_memory": selection.read_memory,
            "write_memory": selection.write_memory,
            "shared_memory_access": "none",
            "transcript_policy": selection.transcript_policy,
            "assistant_identity": [SYSTEM_ASSISTANT_IDENTITY],
        }
        return ResolvedInteractionContext(**payload, effective_identity_hash=_identity_hash(payload))

    if not character_mode_enabled():
        raise CharacterModeDisabledError("Character Mode is disabled")
    if not selection.character_id:
        raise CharacterResolutionError("character mode requires character_id")
    if character is None:
        raise CharacterResolutionError("character profile was not resolved by the server")
    if character.id != selection.character_id:
        raise CharacterResolutionError("resolved character does not match character_id")
    if not character.enabled:
        raise CharacterResolutionError("character profile is disabled")

    # Keep governance validation server-side, but do not turn policy metadata or
    # generic assistant wording into competing model instructions. Character
    # Mode has one authoritative persona prompt: the saved personality prompt.
    _validated_identity_policy(character)
    if selection.shared_memory_access != "none":
        if not character_shared_memory_enabled():
            raise CharacterInteractionError("shared character memory access is disabled")
        _validate_shared_memory_policy(character)
    if (selection.read_memory or selection.write_memory) and not character_memory_enabled():
        raise CharacterInteractionError("character memory is disabled")

    # A character's governed default voice is authoritative for Character Mode.
    # The session selection remains a fallback for legacy profiles without one.
    voice_asset_id = selection.voice_asset_id or character.default_voice_asset_id
    assistant_identity = [character.personality_prompt.strip()]
    payload = {
        "interaction_mode": "character",
        "owner_type": "character",
        "owner_id": character.id,
        "display_name": character.display_name,
        "character_id": character.id,
        "voice_asset_id": voice_asset_id,
        "read_memory": selection.read_memory,
        "write_memory": selection.write_memory,
        "shared_memory_access": selection.shared_memory_access,
        "transcript_policy": selection.transcript_policy,
        "character_profile_version": character.version,
        "assistant_identity": assistant_identity,
    }
    return ResolvedInteractionContext(**payload, effective_identity_hash=_identity_hash(payload))


def resolve_system_session_identity(session: object) -> ResolvedInteractionContext:
    """Resolve a persisted Chat session through backend-owned identity data."""

    selection = InteractionSelection(
        interaction_mode=getattr(session, "interaction_mode", "system"),
        character_id=getattr(session, "character_id", None),
        voice_asset_id=getattr(session, "voice_asset_id", None),
        read_memory=bool(getattr(session, "read_memory", False)),
        write_memory=bool(getattr(session, "write_memory", False)),
        shared_memory_access=getattr(session, "shared_memory_access", "none"),
        transcript_policy=getattr(session, "transcript_policy", "persistent"),
    )
    character = None
    if selection.interaction_mode == "character":
        try:
            from .service import default_character_service

            character = default_character_service().resolve_snapshot(selection.character_id or "")
        except Exception as exc:
            raise CharacterResolutionError("persisted character profile could not be resolved") from exc
    return resolve_interaction_context(selection, character=character)
