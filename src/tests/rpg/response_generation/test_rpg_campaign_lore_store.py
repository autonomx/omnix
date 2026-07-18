from __future__ import annotations

from app.rpg.session.genesis.campaign_lore_store import (
    current_location_identity,
    ensure_current_location_document,
)


class _Gateway:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt, *, context, timeout_s):
        self.calls += 1
        assert "Campaign Bible entry" in prompt
        assert context["location"]["name"] == "Rusty Flagon Tavern"
        assert timeout_s == 20.0
        return (
            "The Rusty Flagon Tavern stands at a busy meeting point for travelers and local workers. "
            "Its warm common room smells of hearth smoke, bread, and rain-damp wool, while regulars trade news beneath scarred beams. "
            "Rooms, meals, and conversation make it both a refuge and a practical source of information about the surrounding roads."
        )


def _session() -> dict:
    return {
        "manifest": {"session_id": "campaign:elara", "title": "Elara"},
        "state": {
            "current_location": "Rusty Flagon Tavern",
            "metadata": {"genre": "classic_fantasy", "tone": "grounded"},
        },
    }


def test_current_location_identity_normalizes_legacy_location_strings() -> None:
    assert current_location_identity(_session()) == {
        "id": "location:rusty-flagon-tavern",
        "name": "Rusty Flagon Tavern",
    }


def test_missing_current_location_lore_is_generated_once_and_made_public() -> None:
    gateway = _Gateway()
    bible = {
        "canon_revision": 0,
        "documents": [],
        "entities": {},
        "discovery_state": {"pages": {}, "entities": {}, "discoveries": []},
    }

    updated, document_id, generated = ensure_current_location_document(
        bible,
        _session(),
        canon_revision=1,
        llm_gateway=gateway,
    )

    assert generated is True
    assert document_id == "lore:location:rusty-flagon-tavern"
    assert gateway.calls == 1
    document = updated["documents"][0]
    assert document["title"] == "Rusty Flagon Tavern"
    assert document["topic_id"] == "locations"
    assert document["visibility"] == "public"
    assert updated["discovery_state"]["pages"][document_id] == "public_at_campaign_start"
    assert updated["entities"]["location:rusty-flagon-tavern"]["kind"] == "location"

    unchanged, repeated_id, repeated = ensure_current_location_document(
        updated,
        _session(),
        canon_revision=2,
        llm_gateway=gateway,
    )
    assert repeated is False
    assert repeated_id == document_id
    assert len(unchanged["documents"]) == 1
    assert gateway.calls == 1
