"""Synchronize durable live delivery checkpoints into stored chat metadata."""
from __future__ import annotations

from .assistant_turns import AssistantTurnRecord


def sync_delivery_metadata(record: AssistantTurnRecord) -> bool:
    """Copy one coordinator checkpoint into its persisted user and assistant messages."""
    from .character_store import default_chat_store

    store = default_chat_store()
    metadata = _metadata(record)
    targeted_update = getattr(store, "update_delivery_metadata", None)
    if callable(targeted_update):
        return bool(
            targeted_update(
                session_id=record.session_id,
                assistant_turn_id=record.assistant_turn_id,
                metadata=metadata,
            )
        )

    # Compatibility fallback for non-PostgreSQL stores. The active runtime uses
    # the targeted metadata update above so delivery checkpoints never serialize
    # the entire chat workspace against an immediately following voice turn.
    sessions = store._load_sessions()
    changed = False
    for session_index, session in enumerate(sessions):
        if session.id != record.session_id:
            continue
        for message in session.messages:
            if message.metadata.get("assistant_turn_id") != record.assistant_turn_id:
                continue
            message.metadata.update(metadata)
            changed = True
        if changed:
            sessions[session_index] = session
            store._save_sessions(sessions)
        return changed
    return False


def _metadata(record: AssistantTurnRecord) -> dict[str, object]:
    return {
        "generated_phrase_count": record.generated_phrase_count,
        "audio_delivered_phrase_count": record.audio_delivered_phrase_count,
        "audio_interrupted_phrase_index": record.audio_interrupted_phrase_index,
        "audio_played_samples": record.audio_played_samples,
        "visual_delivered_text_end": record.visual_delivered_text_end,
        "context_delivered_text_end": record.context_delivered_text_end,
        "delivery_policy": record.delivery_policy,
    }
