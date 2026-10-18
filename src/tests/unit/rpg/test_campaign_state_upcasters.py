"""Saved campaigns of every schema version load in the current shape (WP-5.6)."""
from __future__ import annotations

import copy

import pytest

from app.apps.rpg.session.campaign_state import (
    CURRENT_SCHEMA_VERSION,
    UPCASTERS,
    CampaignState,
    schema_version,
    upcast_campaign_document,
    upcast_if_outdated,
)


def _historical(version: int | str | None) -> dict:
    """A save as version ``version`` wrote it: no ambient runtime, interactions only in the transcript."""
    manifest = {"id": "session:old", "title": "Old Road"}
    if version is not None:
        manifest["schema_version"] = version
    return {
        "manifest": manifest,
        "state": {"location": "Rusty Flagon Tavern"},
        "simulation_state": {"tick": 3, "player_state": {"level": 2}},
        "runtime_state": {
            "transcript": [
                {"role": "player", "text": "I greet Bran.", "turn_id": "turn:3", "tick": 3},
                {"role": "assistant", "speaker_id": "npc:bran", "speaker": "Bran", "text": "Welcome back."},
            ],
        },
    }


@pytest.mark.parametrize("version", [None, 1, 2, 3, "3", "garbage", True])
def test_versions_before_ambient_narration_gain_the_ambient_runtime_and_timeline(version) -> None:
    upcast = upcast_campaign_document(_historical(version))
    state = CampaignState.model_validate(upcast)
    assert state.manifest.schema_version == CURRENT_SCHEMA_VERSION
    assert state.manifest.session_id == "session:old"
    runtime = state.runtime_state
    assert runtime["ambient_queue"] == [] and runtime["subscription_state"] == {"last_polled_seq": 0}
    assert runtime["interaction_timeline"]["events"], "the legacy transcript becomes interaction events"
    assert runtime["transcript"], "legacy data is kept"
    assert state.simulation_state["presentation_state"] == {} and state.simulation_state["memory_state"] == {}


def test_version_four_keeps_its_runtime_and_gains_the_timeline() -> None:
    document = _historical(4)
    document["runtime_state"]["ambient_seq"] = 7
    upcast = upcast_campaign_document(document)
    assert upcast["runtime_state"]["ambient_seq"] == 7
    assert "ambient_queue" not in upcast["runtime_state"], "version 4 already had its ambient runtime"
    assert upcast["runtime_state"]["interaction_timeline"]["events"]
    assert schema_version(upcast) == CURRENT_SCHEMA_VERSION


def test_upcasting_is_idempotent_and_a_current_document_loads_as_stored() -> None:
    once = upcast_campaign_document(_historical(1))
    assert upcast_campaign_document(copy.deepcopy(once)) == once
    current = {**copy.deepcopy(once), "unknown_section": {"kept": True}}
    assert upcast_if_outdated(current) is current


def test_an_outdated_document_is_upcast_on_load() -> None:
    loaded = upcast_if_outdated(_historical(2))
    assert schema_version(loaded) == CURRENT_SCHEMA_VERSION
    assert loaded["runtime_state"]["ambient_queue"] == []


def test_upcasters_are_ordered_and_reach_at_most_the_current_version() -> None:
    targets = [target for target, _ in UPCASTERS]
    assert targets == sorted(set(targets))
    assert all(1 < target <= CURRENT_SCHEMA_VERSION for target in targets)
