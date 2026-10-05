"""Chat resolves who a session speaks as through the CHARACTER_RESOLVER port (PA-1.3)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.platform.chat import session_identity
from app.platform.chat.contracts import CHARACTER_RESOLVER
from app.conversation.contracts import (
    SYSTEM_ASSISTANT_ID,
    CharacterModeDisabledError,
    CharacterResolutionError,
    InteractionSelection,
)
from app.runtime.ports import PortBinding, PortBindings, install_port_bindings


def _session(**values) -> SimpleNamespace:
    return SimpleNamespace(**{"interaction_mode": "system", "character_id": None, "shared_memory_access": "none", **values})


@pytest.fixture
def without_characters():
    install_port_bindings(PortBindings({}))


def test_without_characters_chat_still_serves_the_system_assistant(without_characters) -> None:
    identity = session_identity.resolve_system_session_identity(_session())

    assert identity.owner_id == SYSTEM_ASSISTANT_ID
    assert session_identity.character_mode_available() is False
    assert session_identity.resolve_shared_memory_categories(_session()) == []
    with pytest.raises(CharacterModeDisabledError, match="Character Mode is disabled"):
        session_identity.resolve_system_session_identity(_session(interaction_mode="character", character_id="maya"))


class _Resolver:
    def __init__(self, snapshot_error: Exception | None = None) -> None:
        self.snapshot_error = snapshot_error

    def mode_enabled(self) -> bool:
        return True

    def resolve_snapshot(self, character_id: str):
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return SimpleNamespace(id=character_id)

    def resolve_character(self, selection, snapshot):
        return SimpleNamespace(owner_id=snapshot.id, selection=selection)

    def shared_memory_categories(self, session) -> list[str]:
        return ["fact"]


def _bind(resolver) -> None:
    install_port_bindings(PortBindings.build([PortBinding(CHARACTER_RESOLVER, resolver, owner="characters")]))


def test_a_character_session_is_resolved_by_the_bound_resolver() -> None:
    _bind(_Resolver())
    selection = InteractionSelection(interaction_mode="character", character_id="maya")

    context, snapshot = session_identity.resolve_selection(selection)

    assert (context.owner_id, snapshot.id) == ("maya", "maya")
    assert session_identity.character_mode_available() is True
    assert session_identity.resolve_shared_memory_categories(
        _session(interaction_mode="character", character_id="maya", shared_memory_access="read_only")
    ) == ["fact"]


def test_a_persisted_character_that_cannot_be_resolved_is_a_resolution_error_but_a_request_sees_the_cause() -> None:
    _bind(_Resolver(snapshot_error=KeyError("maya")))
    persisted = _session(interaction_mode="character", character_id="maya")

    with pytest.raises(CharacterResolutionError, match="persisted character profile could not be resolved"):
        session_identity.resolve_system_session_identity(persisted)
    with pytest.raises(KeyError):
        session_identity.resolve_selection(InteractionSelection(interaction_mode="character", character_id="maya"))
