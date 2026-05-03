from app.rpg.memory.causal_retrieval import retrieve_causal_memories
from app.rpg.memory.observation import record_event_observations, record_told_memory
from tests.rpg.spatial.fixtures import tavern_spatial_fixture, tavern_spatial_fixture_with_private_door_open


def test_same_room_npc_observes_event():
    simulation_state = {"spatial_graph": tavern_spatial_fixture()}
    event = {
        "event_id": "evt:player_greets_bran",
        "actor_id": "player",
        "target_id": "bran",
        "location_id": "tavern_common_room",
        "summary": "The player greeted Bran.",
        "tags": ["social"],
    }

    result = record_event_observations(simulation_state, event, turn_index=1)
    rows = retrieve_causal_memories(simulation_state, "bran", actor_id="player")

    assert result["ok"] is True
    assert rows
    assert rows[0]["kind"] == "affected"


def test_private_room_event_not_seen_by_common_room_npc_when_door_closed():
    simulation_state = {"spatial_graph": tavern_spatial_fixture()}
    event = {
        "event_id": "evt:private_whisper",
        "actor_id": "guest_private",
        "target_id": "spy",
        "location_id": "private_room",
        "summary": "A private whisper happened in the room.",
        "tags": ["private"],
        "sound_level": "quiet",
    }

    record_event_observations(simulation_state, event, turn_index=2)
    bran_rows = retrieve_causal_memories(simulation_state, "bran", tags=["private"])

    assert bran_rows == []


def test_closed_door_normal_sound_is_heard_as_muffled():
    simulation_state = {"spatial_graph": tavern_spatial_fixture()}
    event = {
        "event_id": "evt:private_argument",
        "actor_id": "guest_private",
        "target_id": "spy",
        "location_id": "private_room",
        "summary": "A muffled argument came from the private room.",
        "tags": ["argument"],
        "sound_level": "normal",
    }

    record_event_observations(simulation_state, event, turn_index=3)
    rows = retrieve_causal_memories(simulation_state, "bran", tags=["argument"])

    assert rows
    assert rows[0]["kind"] == "heard"
    assert rows[0]["confidence"] < 1.0


def test_told_memory_is_unverified_claim_by_default():
    simulation_state = {}
    result = record_told_memory(
        simulation_state,
        "bran",
        speaker_id="player",
        event_id="evt:claim_bandits",
        summary="The player claimed bandits were nearby.",
        facts={"actor_id": "bandits", "location_id": "road"},
        turn_index=4,
    )

    rows = retrieve_causal_memories(simulation_state, "bran", tags=["claim"])

    assert result["ok"] is True
    assert rows
    assert "unverified" in rows[0]["tags"]
    assert rows[0]["confidence"] < 1.0


def test_save_load_preserves_causal_memory_state_json_shape():
    import json

    simulation_state = {"spatial_graph": tavern_spatial_fixture()}
    event = {
        "event_id": "evt:save_load",
        "actor_id": "player",
        "target_id": "bran",
        "location_id": "tavern_common_room",
        "summary": "The player spoke to Bran.",
        "tags": ["social"],
    }
    record_event_observations(simulation_state, event, turn_index=5)

    encoded = json.dumps(simulation_state, sort_keys=True)
    decoded = json.loads(encoded)

    rows = retrieve_causal_memories(decoded, "bran", actor_id="player")
    assert rows


def test_hidden_target_event_not_recorded_from_actor_visibility_only():
    simulation_state = {"spatial_graph": tavern_spatial_fixture_with_private_door_open()}
    event = {
        "event_id": "evt:manual_private_room_quiet_event",
        "actor_id": "guest_private",
        "target_id": "spy",
        "location_id": "private_room",
        "summary": "A quiet private exchange happened in the private room.",
        "tags": ["private", "quiet"],
        "sound_level": "quiet",
    }

    record_event_observations(simulation_state, event, turn_index=1)
    player_rows = retrieve_causal_memories(simulation_state, "player", target_id="spy")

    assert player_rows == []


def test_actor_only_event_can_be_observed_when_no_hidden_target():
    simulation_state = {"spatial_graph": tavern_spatial_fixture_with_private_door_open()}
    event = {
        "event_id": "evt:manual_actor_only_public_event",
        "actor_id": "guest_private",
        "location_id": "private_room",
        "summary": "A public actor-only event in the private room.",
        "tags": ["public_actor_only"],
        "sound_level": "normal",
    }

    record_event_observations(simulation_state, event, turn_index=1)
    player_rows = retrieve_causal_memories(simulation_state, "player", actor_id="guest_private")

    assert player_rows
    assert player_rows[0]["kind"] == "observed"