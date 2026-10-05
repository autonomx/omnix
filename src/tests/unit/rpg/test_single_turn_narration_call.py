"""A turn narrates once: the authoritative chain skips its synchronous narration
when the runtime narration stage will call the provider (WP-8.6)."""
from __future__ import annotations

from app.apps.rpg.session.deferred_narration_guard import runtime_narration_follows_context
from app.apps.rpg.session.llm_narration_projection import _phase8_part31_should_sync_narration

PAYLOAD = {"narration_request": {"scene": {"location_name": "Tavern"}, "narration_context": {"turn": 1}}}


def test_the_projection_narrates_when_no_runtime_narration_follows() -> None:
    assert _phase8_part31_should_sync_narration(PAYLOAD) is True


def test_the_projection_skips_when_runtime_narration_follows() -> None:
    with runtime_narration_follows_context(True):
        assert _phase8_part31_should_sync_narration(PAYLOAD) is False
    assert _phase8_part31_should_sync_narration(PAYLOAD) is True
