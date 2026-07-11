"""Policy-authorized proactive live-conversation turns and delivery persistence."""
from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app import shared
from app.providers import ChatMessage as ProviderMessage

from .models import ChatMessage, ChatSession
from .store import _model_key, _provider_key, _pop_ready_sentences

PROACTIVE_MAX_CHARS = 320
PROACTIVE_MAX_WORDS = 42


class ProactiveDeliveryRequest(BaseModel):
    turn_id: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=PROACTIVE_MAX_CHARS)
    initiative_reason: str = Field(min_length=1, max_length=120)
    topic_id: str | None = Field(default=None, max_length=120)
    delivery_status: Literal["completed", "interrupted"] = "completed"
    interrupted_at_phrase: int | None = Field(default=None, ge=0)


class ProactiveDeliveryResponse(BaseModel):
    session: ChatSession
    message_id: str
    duplicate: bool = False


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip().strip(' \t\r\n"“”')
    words = compact.split()
    if len(words) > PROACTIVE_MAX_WORDS:
        compact = " ".join(words[:PROACTIVE_MAX_WORDS]).rstrip(" ,;:-")
    if len(compact) > PROACTIVE_MAX_CHARS:
        compact = compact[:PROACTIVE_MAX_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:-")
    if compact and compact[-1] not in ".!?":
        compact += "."
    return compact


def _prompt(reason: str, state_summary: str | None) -> str:
    context = (state_summary or "").strip()
    return (
        "The live voice conversation is quiet and deterministic policy has authorized one proactive move. "
        f"Initiative reason: {reason.strip()}. "
        "Respond as the established character in one short, natural spoken turn under 42 words. Continue an "
        "unresolved thread, ask one relevant follow-up, or offer one useful next step. Do not mention timers, "
        "dead air, policy, prompting, or being an AI. Do not pressure the user and do not ask more than one question."
        + (f" Current live-conversation state: {context}" if context else "")
    )


def stream_proactive_turn_chunks(
    store: Any,
    session: ChatSession,
    *,
    initiative_reason: str,
    state_summary: str | None = None,
    provider_id: str | None = None,
    model_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    resolved_provider_id = provider_id or session.provider_id
    resolved_model_id = model_id or session.model_id
    provider = shared.get_provider(_provider_key(resolved_provider_id))
    if provider is None:
        raise RuntimeError("Chat provider is not available")

    turn_id = f"proactive:{uuid.uuid4().hex}"
    synthetic_message = ChatMessage(
        id=turn_id,
        role="user",
        content=_prompt(initiative_reason, state_summary),
        created_at=_utcnow(),
        metadata={"source": "proactive_reengagement", "transient": True},
    )
    provider_messages = store._provider_messages(session, synthetic_message, [])
    messages = [ProviderMessage(role=message.role, content=message.content) for message in provider_messages]
    model_name = _model_key(resolved_model_id)
    response = provider.chat_completion(messages=messages, model=model_name, stream=True)
    pending = ""
    full_text = ""
    resolved_model = model_name
    usage = None
    proactive_text = ""
    try:
        for chunk in response:
            text = getattr(chunk, "content", "") or ""
            if not text:
                continue
            resolved_model = getattr(chunk, "model", None) or resolved_model
            usage = getattr(chunk, "usage", None) or usage
            full_text += text
            pending += text
            ready, pending = _pop_ready_sentences(pending)
            if ready:
                proactive_text = _normalize(ready[0])
                break
            if len(pending) >= PROACTIVE_MAX_CHARS:
                proactive_text = _normalize(pending)
                break
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()

    proactive_text = proactive_text or _normalize(pending or full_text)
    if not proactive_text:
        raise RuntimeError("Proactive live-conversation response was empty")

    yield {"type": "initiative", "turn_id": turn_id, "initiative_reason": initiative_reason}
    yield {"type": "text_chunk", "text": proactive_text}
    yield {
        "type": "complete",
        "content": proactive_text,
        "metadata": {
            "generation_status": "completed",
            "purpose": "proactive_reengagement",
            "transient": True,
            "turn_id": turn_id,
            "initiative_reason": initiative_reason,
            "provider_id": resolved_provider_id,
            "model_id": resolved_model_id,
            "resolved_model": resolved_model,
            **({"usage": usage} if usage else {}),
        },
    }


def commit_proactive_delivery(store: Any, session_id: str, request: ProactiveDeliveryRequest) -> ProactiveDeliveryResponse | None:
    current = store.get_session(session_id)
    if current is None:
        return None
    for message in current.messages:
        if message.role == "assistant" and message.metadata.get("turn_id") == request.turn_id:
            return ProactiveDeliveryResponse(session=current, message_id=message.id, duplicate=True)

    metadata: dict[str, Any] = {
        "generation_status": "completed",
        "purpose": "proactive_reengagement",
        "turn_id": request.turn_id,
        "initiative_reason": request.initiative_reason,
        "delivery_status": request.delivery_status,
    }
    if request.topic_id:
        metadata["topic_id"] = request.topic_id
    if request.interrupted_at_phrase is not None:
        metadata["interrupted_at_phrase"] = request.interrupted_at_phrase
    session = store.complete_streamed_reply(session_id, f"{request.turn_id}:no-user", request.content, metadata)
    if session is None:
        return None
    message = session.messages[-1]
    return ProactiveDeliveryResponse(session=session, message_id=message.id)


__all__ = [
    "ProactiveDeliveryRequest",
    "ProactiveDeliveryResponse",
    "commit_proactive_delivery",
    "stream_proactive_turn_chunks",
]
