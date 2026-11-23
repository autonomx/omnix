"""Chat owns how it asks the agent runtime about a typed turn and what it keeps of the answer (deep-modules wave 2)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.platform.chat import turn_routing
from app.platform.chat.turn_routing import (
    ROUTING_METADATA_KEYS,
    patch_user_message_metadata,
    persist_routing_metadata,
    route_typed_turn,
)


class _Store:
    def __init__(self) -> None:
        self.discarded: list[str] = []
        self.built: list[list] = []

    def build_routing_context(self, session, user_message, context_items):
        self.built.append(context_items)
        return {"reference_context": "earlier turns"}

    def discard_prompt_context(self, session, user_message) -> None:
        self.discarded.append(user_message.id)


def _turn():
    return SimpleNamespace(id="s1", provider_id="lmstudio"), SimpleNamespace(id="m1", role="user", metadata={})


@pytest.fixture
def router(monkeypatch):
    seen: dict = {}

    def fake(session, user_message, **options):
        seen.update(options)
        factory = options.get("routing_context_factory")
        seen["context"] = factory() if factory else None
        return seen.get("result")

    monkeypatch.setattr("app.platform.chat.contracts.route_typed_turn", fake)
    monkeypatch.setattr(turn_routing, "provider_turn_deadline", lambda *a, existing_deadline_at=None, **k: (
        existing_deadline_at if existing_deadline_at is not None else 99.0))
    return seen


def test_a_settled_turn_reads_chat_context_and_drops_the_unused_prompt(router) -> None:
    store, (session, message) = _Store(), _turn()
    router["result"] = SimpleNamespace(content="started", metadata={})

    result = route_typed_turn(store, session, message, provider_id="lmstudio", model_id=None, context_items=None)

    assert result.content == "started"
    assert router["context"] == {"reference_context": "earlier turns"} and store.built == [[]]
    assert router["routing_deadline_at"] == 99.0
    assert store.discarded == ["m1"]


def test_chat_answers_when_the_router_declines_and_keeps_the_callers_deadline(router) -> None:
    store, (session, message) = _Store(), _turn()

    assert route_typed_turn(store, session, message, provider_id=None, model_id=None, routing_deadline_at=5.0) is None
    assert router["routing_deadline_at"] == 5.0
    assert store.discarded == []


def test_routing_metadata_is_stored_on_the_user_message_only() -> None:
    user = SimpleNamespace(id="m1", role="user", metadata={})
    reply = SimpleNamespace(id="m1", role="assistant", metadata={})
    saved: list = []
    store = SimpleNamespace(
        get_session=lambda _id: SimpleNamespace(messages=[reply, user]),
        _save_session=saved.append,
    )
    routed = SimpleNamespace(id="m1", metadata={"omnix_route": {"lane": "agent"}, "unrelated": 1})

    persist_routing_metadata(store, SimpleNamespace(id="s1"), routed)

    assert user.metadata == {"omnix_route": {"lane": "agent"}} and reply.metadata == {} and len(saved) == 1
    assert "omnix_route" in ROUTING_METADATA_KEYS


def test_a_store_with_a_targeted_update_is_patched_through_it() -> None:
    calls: list = []
    store = SimpleNamespace(update_user_message_metadata=lambda **kwargs: calls.append(kwargs))

    patch_user_message_metadata(store, session_id="s1", message_id="m1", metadata={"a": 1})
    patch_user_message_metadata(store, session_id="s1", message_id="m1", metadata={})

    assert calls == [{"session_id": "s1", "message_id": "m1", "metadata": {"a": 1}}]
